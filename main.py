import asyncio
from aiohttp import web
from PIL import Image, ImageFont, ImageDraw 
import socket, qrcode
import glob, os
from tempfile import TemporaryFile
from qrcode.image.pure import PymagingImage
from aiohttp import streamer
from urllib import parse
from tqdm import tqdm

@streamer
async def file_sender(writer, file_path=None):
	"""
	This function will read large file chunk by chunk and send it through HTTP
	without reading them into memory
	"""
	with open(file_path, 'rb') as f:
		progress=tqdm(desc=file_path,unit="bytes",unit_scale=True,total=os.path.getsize(file_path))
		chunk = f.read(2 ** 16)
		progress.update(len(chunk))
		while chunk:
			await writer.write(chunk)
			chunk = f.read(2 ** 16)
			progress.update(len(chunk))

async def getcia(request):
	headers = {
		"Content-disposition": "attachment; filename={file_name}".format(file_name=request.path[1:]),
		"content-type":"application/zip",
		"accept-ranges":"bytes",
		"content-length":str(os.path.getsize(request.path[1:]))
	}
	
	if not os.path.exists(request.path[1:]):
		return web.Response(
			body='File <{file_name}> does not exist'.format(file_name=request.path[1:]),
			status=404
		)
	
	return web.Response(
		body=file_sender(file_path=request.path[1:]),
		headers=headers
	)

async def main(loop):
	app=web.Application()
	file=[]
	for typ in ['*.cia','*.3dsx']:
		result=glob.glob(typ)
		if result:
			file+=result
	for f in file:
		app.add_routes([web.get('/'+f,getcia)])
	
	if len(file)<=0:
		print('error: please place .cia files in the same directory as this script before running!')
		return
	print('found '+str(len(file))+' file(s) to share with 3ds clients.')
	print('open your homebrew software manager of choice on your device and find the scan qr code option now.\n')

	print('determining ip address...')
	if os.path.exists('ip override.txt'):
		with open('ip override.txt','r') as f:
			ip=f.read()
		print('ip address is '+ip)
		print("if this appears invalid, you can delete 'ip override.txt' to automatically determine the ip.\n")
	else:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(("8.8.8.8", 80))
		ip=s.getsockname()[0]
		s.close()
		print('ip address is '+ip)
		print('please note that this ip detection method requires internet access as it determines which connection you most likely\nshare with the 3ds(es)')
		print("if this is incorrect, create a text file named 'ip override.txt' with your local ip address.\n")

	print('starting web server at '+ip+':8888...')
	
	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, ip, 8888)
	try:
		await site.start()
	except:
		print("ERROR: failed to start the webserver! try changing your ip settings by editing or deleting the 'ip override.txt' file.")
		return
	print('web server running!\n')
	
	for f in file:
		await show_qr(loop,f,ip)
	print("\n\ndone! scan each of these qr codes with each cracked 3ds you want them installed on!")
	print('keep this window open in order to keep the transmission running.')
	print('you can transfer multiple apps to multiple cracked 3dses at once.')

async def show_qr(loop,file,ip):
	print('\nhosting cia at http://'+ip+':8888/'+file+'...\n\ngenerating qr code...')
	with TemporaryFile() as f:
		qrcode.make('http://'+ip+':8888/'+parse.quote_plus(file).replace('+','%20'),image_factory=PymagingImage).save(f)
		img=Image.open(f)
		draw=ImageDraw.Draw(img)
		font = ImageFont.truetype("arial.ttf", 24)
		draw.text((32,0),file,(0,0,0),font=font)
		img.show()

if __name__ == '__main__':
	loop = asyncio.get_event_loop()
	loop.create_task(main(loop))
	try:
		loop.run_forever()
	except KeyboardInterrupt:
		pass
