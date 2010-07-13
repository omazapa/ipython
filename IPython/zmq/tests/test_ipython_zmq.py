# -*- coding: utf-8 -*-
import sys
from IPython.zmq.frontend import InteractiveShellFrontend
from IPython.zmq.kernel   import InteractiveShellKernel, OutStream, DisplayHook
from IPython.zmq.session import Session
import nose.tools as nt
import zmq, time
from threading import Thread
orig_stdout = sys.stdout
orig_stderr = sys.stderr

def kernel():
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
        
        kern = InteractiveShellKernel(session, reply_socket, pub_socket,request_socket)
        #init kernel but just wait one request and stop
        kern.test()
        
        

def test_ipython_zmq():
        # init kernel test in a thread
        thread=Thread(target=kernel)
        thread.start()
        #wait that kernel start
        time.sleep(2)
        
        ip = '127.0.0.1'
        print >> orig_stdout, ip
        #ip = '99.146.222.252'
        port_base = 5555
        connection = ('tcp://%s' % ip) + ':%i'
        req_conn = connection % port_base
        sub_conn = connection % (port_base+1)
        rep_conn = connection % (port_base+2)

        # Create initial sockets
        c = zmq.Context(1)
        request_socket = c.socket(zmq.XREQ)
        request_socket.connect(req_conn)

        sub_socket = c.socket(zmq.SUB)
        sub_socket.connect(sub_conn)
        sub_socket.setsockopt(zmq.SUBSCRIBE, '')

        reply_socket = c.socket(zmq.REP)
        reply_socket.connect(rep_conn)

        # Make session and user-facing client
        sess = Session()  
        frontend=InteractiveShellFrontend('<zmq-console>',sess,request_socket=request_socket,subscribe_socket=sub_socket,reply_socket=reply_socket)
        code="print 'hello'"
        output=frontend.test(code)
        
        #test if status of message is ok using nose.tools
        nt.assert_equals(output['content']['status' ],'ok')
