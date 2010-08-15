# -*- coding: utf-8 -*-
import sys
from IPython.zmq.frontend import Frontend
from IPython.zmq.kernel   import InteractiveShellKernel, OutStream, DisplayHook
from IPython.zmq.session import Session
from IPython.zmq.kernelmanager import KernelManager
import nose.tools as nt
import zmq, time
from threading import Thread
orig_stdout = sys.stdout
orig_stderr = sys.stderr

kernel = None
frontend = None

def kernel_connection():
   c = zmq.Context(1)
     
   ip = '127.0.0.1'
   port_base = 5555
   connection = ('tcp://%s' % ip) + ':%i'
   rep_conn = connection % port_base
   pub_conn = connection % (port_base+1)
   req_conn = connection % (port_base+2)
        
   print >>sys.__stdout__, "Starting the kernel..."
   print >>sys.__stdout__, "On:",rep_conn, pub_conn
        
   session = Session(username=u'kernel')
        
   reply_socket = c.socket(zmq.XREP)
   reply_socket.bind(rep_conn)
        
   pub_socket = c.socket(zmq.PUB)
   pub_socket.bind(pub_conn)
        
        
   request_socket = c.socket(zmq.REQ)
   request_socket.bind(req_conn)
        
   kernel = InteractiveShellKernel(session, reply_socket, pub_socket,request_socket) 
   #kernel.interact()
   kernel.start()

def test_start_kernel():
   thread=Thread(target=kernel_connection)
   thread.start()     
        

def test_ipython_zmq():
   
   #wait that kernel start
   time.sleep(5)
   xreq_addr = ('127.0.0.1',5555)
   sub_addr = ('127.0.0.1', 5556)
   rep_addr = ('127.0.0.1', 5557)
   context = zmq.Context()
   session = Session()
   
   km = KernelManager(xreq_addr, sub_addr, rep_addr,context,None)
   
   # Make session and user-facing client
   frontend=Frontend(km)   
   code="print 'hello'"
   print >>orig_stdout,"Sending Message"
   #frontend.runcode(code)
   reply_msg = frontend.send_noninteractive_request(code)
   reply_msg = frontend.recv_noninteractive_reply()
   pyin_msg = frontend.recv_noninteractive_reply()
   output_msg = frontend.recv_noninteractive_reply()
   print >>orig_stdout,"Recieved Message"
   print >>orig_stdout, reply_msg
   print >>orig_stdout, output_msg
   #test if status of message is ok using nose.tools
   nt.assert_equals(reply_msg['content']['status'],'ok')
   nt.assert_equals(pyin_msg['content']['code'],code)
   nt.assert_equals(output_msg['content']['data'],'hello')
   print >> orig_stdout,"Test passed"

def test_stop_kernel():
   kernel.stop()     

if __name__ == "__main__" :
   test_start_kernel()       
   test_ipython_zmq()
   #test_stop_kernel()
   #test_stop_kernel()

