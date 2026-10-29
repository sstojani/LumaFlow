import asyncio
import json
import threading
from http.server import HTTPServer,BaseHTTPRequestHandler
from adapters import WLED

def test_wled_against_local_http_server():
    payloads=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps({'info':{'ver':'test'},'state':{'seg':[{'id':0,'start':0,'stop':30}]}}).encode())
        def do_POST(self):
            payloads.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200);self.end_headers();self.wfile.write(b'{"success":true}')
    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    async def work():
        adapter=WLED({'address':f'127.0.0.1:{server.server_port}'})
        await adapter.connect();await adapter.send((255,0,0),25);await adapter.close()
    try:
        asyncio.run(work());assert payloads[0]['bri']==64;assert payloads[0]['seg'][0]['col']==[[255,0,0]]
    finally:server.shutdown();server.server_close();thread.join()
