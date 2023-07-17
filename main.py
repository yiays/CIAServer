"""
    CIAServer
    Hosts rom files with QR codes locally so homebrew apps like FBI can download and install them
"""

import glob
import os
import base64
import webbrowser
from io import BytesIO
from urllib import parse
import asyncio
from aiohttp import web
import aiofiles
from tqdm import tqdm
import qrcode

qrcodes: dict[str, str] = {}

indexpage = """<!DOCTYPE html>
<html lang="en">
<head>
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
        }
        .qr h2 {
            margin: 0;
        }
    </style>
</head>
<body>
    <h1>Your CIAServer is running!</h1>
    <p class="lead">
        Keep the terminal window open to keep the server online.
    </p>
    <p>
        Any 2DS/3DS/N2DS/N3DS connected to the same WiFi network should be able to scan these QR
        codes and install software via FBI <i>(In Scan QR Code mode)</i>.
    </p>
    <main>
        {{content}}
    </main>
</body>"""

async def file_sender(file_path):
    """
    Streams files without loading into memory
    """
    chunk_size = 2 ** 16
    file_size = os.path.getsize(file_path)
    progress = tqdm(desc=file_path, unit="bytes", unit_scale=True, total=file_size)

    async with aiofiles.open(file_path, 'rb') as f:
        while True:
            chunk = await f.read(chunk_size)
            if not chunk:
                break
            yield chunk
            progress.update(len(chunk))

async def get_cia(request:web.Request):
    """ Respond to GET requests with the rom file """
    headers = {
        "Content-disposition": f"attachment; filename={request.path[1:]}",
        "content-type":"application/zip",
        "accept-ranges":"bytes",
        "content-length":str(os.path.getsize(request.path[1:]))
    }

    if not os.path.exists(request.path[1:]):
        return web.Response(
            body=f"File <{request.path[1:]}> does not exist",
            status=404
        )

    response = web.StreamResponse(headers=headers)
    response.enable_chunked_encoding()

    async def stream_file():
        async for chunk in file_sender(request.path[1:]):
            await response.write(chunk)

    await response.prepare(request)
    await stream_file()

    return response

async def get_home(request:web.Request):
    headers = {
        'content-type': 'text/html'
    }
    content = '\n'.join(
        (f"""
        <div class="qr">
            <img src="data:image/png;base64,{data}">
            <h2>{file}</h2>
        </div>""" for file,data in qrcodes.items())
    )
    return web.Response(
        body=indexpage.replace('{{content}}', content),
        headers=headers
    )

async def main():
    """ Main loop """
    global qrcodes

    app=web.Application()
    # Find rom files and create routes
    roms=[]
    for typ in ['*.cia','*.3dsx']:
        result=glob.glob(typ)
        if result:
            roms+=result
    app.add_routes([web.get('/'+parse.quote_plus(f).replace('+','%20'),get_cia) for f in roms])
    app.router.add_get('/', get_home)

    if len(roms)<=0:
        print('error: please place .cia files in the same directory as this script before running!')
        return
    print('Found '+str(len(roms))+' file(s) to share with 3ds clients.')
    print('Open your homebrew software manager of choice (FBI) on your device',
          'and find the scan qr code option now.\n')

    ip='0.0.0.0'
    client_ip = 'localhost'
    if os.path.exists('ip override.txt'):
        with open('ip override.txt','r',encoding='ascii') as f:
            ip=f.read()
            client_ip = ip
        print('Manually set IP address is '+ip)
        print("If this appears invalid, you can delete",
              "'ip override.txt' to automatically determine the ip.\n")

    print('starting web server at '+ip+':8888...')

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, ip, 8888)
    try:
        await site.start()
    except OSError:
        print("ERROR: Failed to start the webserver!",
              "Try changing your ip settings by editing or deleting the 'ip override.txt' file.")
        return
    print(f'Web server running at http://{client_ip}:8888 !\n')

    qrcodes = dict((f, generate_qr(f, client_ip)) for f in roms)

    print("\nDone! Scan each of these qr codes with each cracked 3ds you want them installed on!")
    print('Keep this window open in order to keep the transmission running.')
    print('You can transfer multiple apps to multiple cracked 3dses at once.')

    webbrowser.open('http://localhost:8888')

def generate_qr(file, ip):
    """ Create a QR as a Base64 encoded PNG """
    url = 'http://'+ip+':8888/'+parse.quote_plus(file).replace('+','%20')
    print('Hosting rom at '+url+'...\n')

    qr = qrcode.QRCode(border=0)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image()

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
