"""
    CIAServer
    Hosts rom files with QR codes locally so homebrew apps like FBI can download and install them
"""

import glob
import os
import base64
import webbrowser
import socket
import json
from io import BytesIO
from urllib import parse
import asyncio
from aiohttp import web
import aiofiles
import qrcode

ciaserver: "CIAServer"

class CIAServer():
    """ Complete CIAServer module """

    class RomFile:
        """ A RomFile holds all state information for real ROM files found in the cwd """
        file: str
        qrcode: str
        progress: float

        def __init__(self, file: str):
            self.file = file
            self.progress = 0

    class RomFileEncoder(json.JSONEncoder):
        """ Add support for RomFiles to JSONEncoder """
        def default(self, o):
            if isinstance(o, ciaserver.RomFile):
                return o.__dict__
            return super().default(o)

    ip_addr: str
    romfiles: dict[str, RomFile] = {}

    INDEX_PAGE = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CIAServer</title>

        <style>
            html {
                background: #222;
                color: #eee;
                font-size: 14px;
            }
            body {
                display: flex;
                flex-direction: column;
                min-height: calc(100vh - 2rem);
                margin: 0;
                padding: 1rem;
            }
            h1 {
                margin-top: 0;
            }
            .lead {
                font-size: 1.25rem;
            }
            main {
                display: flex;
                flex-grow: 1;
                align-items: center;
                justify-content: center;
                flex-wrap: wrap;
                gap: 1rem;
            }
            .qr {
                display: block;
                text-align: center;
                width: min-content;
                background: #fff;
                color: #000;
                border-radius: 4rem;
                padding: 4rem;
                padding-bottom: 2rem;
            }
            .qr img {
                opacity: 0.125;
                transition: opacity 0.3s;
            }
            .qr:hover img {
                opacity: 1;
            }
            .qr h2 {
                margin: 0;
            }
            .qr progress {
                width: 100%;
            }
        </style>
    </head>
    <body>
        <h1 id="status">Your CIAServer is running!</h1>
        <p class="lead">
            Keep the terminal window open to keep the server online.
        </p>
        <p>
            Any 2DS/3DS/N2DS/N3DS connected to the same WiFi network should be able to scan these QR
            codes and install software via FBI <i>(In Scan QR Code mode)</i>. Hover over a QR code to
            make it easier to scan.
        </p>
        <main id="qrlist"></main>
    </body>
    <script>
        const statusText = document.getElementById('status');
        const qrList = document.getElementById('qrlist');

        function getProgress() {
            fetch("/progress")
                .then(data => data.json())
                .then(updateProgress)
                .catch(error => {
                    console.error(error.message);
                    statusText.innerText = "Your CIAServer has stopped running!";
                    qrList.innerHTML = '';
                    clearTimeout(progressService);
                });
        }

        let listedFiles = [];
        function updateProgress(data) {
            let relistedFiles = [];
            for (const {file, qrcode, progress} of data) {
                relistedFiles.push(file);
                if(listedFiles.indexOf(file) === -1) {
                    let qrDiv = document.createElement('div');
                    qrDiv.classList.add('qr');
                    qrDiv.setAttribute('data-file', file);

                    let qrImg = document.createElement('img');
                    qrImg.src = `data:image/png;base64,${qrcode}`;
                    qrImg.alt = `QR code that downloads ${file}`;
                    qrDiv.appendChild(qrImg);

                    let qrH2 = document.createElement('h2');
                    qrH2.textContent = file;
                    qrDiv.appendChild(qrH2);

                    qrProgress = document.createElement('progress');
                    qrProgress.setAttribute('data-file', file);
                    qrProgress.value = progress * 100;
                    qrProgress.max = 100;
                    qrDiv.appendChild(qrProgress);

                    qrList.appendChild(qrDiv);

                    listedFiles.push(file);
                } else {
                    document.querySelector(`progress[data-file="${file}"]`).value = progress * 100;
                }
            }
            for (file of listedFiles) {
                if(relistedFiles.indexOf(file) === -1) {
                    document.querySelector(`.qr[data-file="${file}"]`).remove();
                    listedFiles.splice(listedFiles.indexOf(file), 1);
                }
            }
            progressService = setTimeout(getProgress, 1000);
        }

        let progressService = setTimeout(getProgress, 1000);
    </script>"""

    async def file_sender(self, file_path):
        """
        Streams files without loading into memory
        """

        chunk_size = 2 ** 16
        file_size = os.path.getsize(file_path)
        total_sent = 0

        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
                total_sent += len(chunk)
                self.romfiles[file_path].progress = total_sent / file_size

    async def get_cia(self, request:web.Request):
        """ Respond to GET requests with the rom file """
        file = request.path[1:]
        print(f"Serving {file}...")

        if not os.path.exists(file):
            return web.Response(body=f"File ({file}) does not exist", status=404)

        headers = {
            "Content-disposition": f"attachment; filename={file.replace(',','_')}",
            "content-type":"application/octet-stream",
            "accept-ranges":"bytes",
            "content-length": str(os.path.getsize(file))
        }

        response = web.StreamResponse(headers=headers)
        async def stream_file():
            async for chunk in self.file_sender(file):
                await response.write(chunk)

        try:
            await response.prepare(request)
            await stream_file()
        except ConnectionResetError:
            print("Connection aborted: other end cancelled.")
            return

        return response

    async def get_home(self, _:web.Request):
        """ Generates an html document full of all generated QR codes """
        headers = {'content-type': 'text/html; charset=utf-8'}
        return web.Response(
            body=self.INDEX_PAGE,
            headers=headers
        )

    async def get_progress(self, _:web.Request):
        """ Respond with a JSON object showing file transfer progress """
        headers = {'content-type': 'application/json; charset=utf-8',
                'cache-control': 'no-cache',
                'x-content-type-options': 'nosniff'}
        content = json.dumps(list(self.romfiles.values()), cls=self.RomFileEncoder)
        return web.Response(body=content, headers=headers)

    async def file_crawler(self):
        """ Maintains a list of rom files that currently exist """

        while True:
            foundroms = []
            for typ in ['*.cia','*.3dsx']:
                for foundfile in glob.glob(typ):
                    foundroms.append(foundfile)
                    if foundfile and (foundfile not in self.romfiles):
                        self.romfiles[foundfile] = self.RomFile(foundfile)
                        print("Found "+foundfile)
                        self.romfiles[foundfile].qrcode = self.generate_qr(foundfile, self.ip_addr)

            for rom in self.romfiles.items():
                if rom not in foundroms:
                    del self.romfiles[rom]
                    break # can't continue iterating once romfiles is changed

            await asyncio.sleep(1)

    async def main(self):
        """ Main process entrypoint """

        app = web.Application()
        app.router.add_get('/', self.get_home)
        app.router.add_get('/progress', self.get_progress)
        app.router.add_get('/{file_path:.+}', self.get_cia)

        if os.path.exists('ip override.txt'):
            with open('ip override.txt','r',encoding='ascii') as f:
                self.ip_addr=f.read()
            print('Manually set IP address is '+self.ip_addr)
            print("If this appears invalid, you can delete",
                "'ip override.txt' to automatically determine the ip.\n")
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                self.ip_addr = s.getsockname()[0]

        # Start the file crawler once the ip address is known
        asyncio.ensure_future(self.file_crawler())

        print('Starting web server at '+self.ip_addr+':8888...')

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.ip_addr, 8888)
        try:
            await site.start()
        except OSError:
            print("ERROR: Failed to start the webserver!",
                "Try changing your ip settings by editing or deleting the 'ip override.txt' file.")
            return
        print(f'Web server running at http://{self.ip_addr}:8888 !\n')

        print(
            "\nDone! Scan each of these qr codes with each cracked 3ds you want them installed on!"
        )
        print('Keep this window open in order to keep the transmission running.')
        print('You can transfer multiple apps to multiple cracked 3dses at once.')

        webbrowser.open(f'http://{self.ip_addr}:8888')

    def generate_qr(self, file, domain):
        """ Create a QR as a Base64 encoded PNG """
        url = 'http://'+domain+':8888/'+parse.quote_plus(file).replace('+','%20')
        print('Hosting rom at '+url+'...\n')

        qr = qrcode.QRCode(border=0)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image()

        buffer = BytesIO()
        img.save(buffer)
        return base64.b64encode(buffer.getvalue()).decode()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    ciaserver = CIAServer()
    loop.create_task(ciaserver.main())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
