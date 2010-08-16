# -*- coding: utf-8 -*-
import sys
from IPython.zmq.frontend import Frontend
from IPython.zmq.kernel   import InteractiveShellKernel, OutStream, DisplayHook, launch_kernel
from IPython.zmq.session import Session
from IPython.zmq.kernelmanager import KernelManager
import nose.tools as nt
import unittest

import zmq, time
from threading import Thread
orig_stdout = sys.stdout
orig_stderr = sys.stderr
from subprocess import Popen

#def test_kernel():
    #thread=Thread(target=kernel_start)
    #thread.start()
    #time.sleep(5)    


class TestKernel(unittest.TestCase):
        
        def setUp(self):
            #thread=Thread(target=kernel_start)
            #thread.start()
            #time.sleep(5)
            
            xreq_addr = ('127.0.0.1',5555)
            sub_addr = ('127.0.0.1', 5556)
            rep_addr = ('127.0.0.1', 5557)
            kernel, xrep, pub, req = launch_kernel(xreq_addr,sub_addr,rep_addr)
            print >>sys.__stdout__, "Starting the kernel"
            context = zmq.Context()
            session = Session()
            km = KernelManager(xreq_addr, sub_addr, rep_addr,context,None)
            print >>sys.__stdout__, "Starting the frontend..."
            self.frontend = Frontend(km)        
        
        
        def test_ipython_zmq_default_values(self):
            #Intial Values
            print >>sys.__stdout__,"KERNEL PID ",self.frontend.kernel_pid    
            nt.assert_equals(self.frontend.kernel_pid,self.frontend.get_kernel_pid())
            print >>sys.__stdout__, "KERNEL/FRONTEND PROMPT ",self.frontend.prompt_count
            nt.assert_equals(self.frontend.prompt_count,1)
        
        def test_request(self):
            #reuqest
            code="print \"hello\""
            print >>sys.__stdout__,"REQUEST",code
            reply_msg  = self.frontend.send_noninteractive_request(code)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            output_msg = self.frontend.recv_noninteractive_reply()
            nt.assert_equals(reply_msg['content']['status'],"ok")
            nt.assert_equals(pyin_msg['content']['code'],code)
            nt.assert_equals(output_msg['content']['data'],"hello")
        def test_system_call(self):    
            #os system call
            code = "!echo 'hello'"
            print >> sys.__stdout__,"SYSTEM CALL ",code
            reply_msg  = self.frontend.send_noninteractive_request(code)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            output_msg = self.frontend.recv_noninteractive_reply()
            
            
            nt.assert_equals(reply_msg['content']['status'],"ok")
            nt.assert_equals(pyin_msg['content']['code'],code)
            nt.assert_equals(output_msg['content']['data'],"hello")
            
            self.frontend.runcode("%pdb")
          
        
        def tearDown(self):
            time.sleep(2)    
            self.frontend.kernel_stop()

            

        
