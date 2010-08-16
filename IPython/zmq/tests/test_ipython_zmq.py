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


class TestKernel(unittest.TestCase):
        
        def setUp(self):
            xreq_addr = ('127.0.0.1',5555)
            sub_addr = ('127.0.0.1', 5556)
            rep_addr = ('127.0.0.1', 5557)
            self.kernel, xrep, pub, req = launch_kernel(xreq_addr,sub_addr,rep_addr)
            print >>sys.__stdout__, "Starting the kernel"
            context = zmq.Context()
            session = Session()
            km = KernelManager(xreq_addr, sub_addr, rep_addr,context,None)
            print >>sys.__stdout__, "Starting the frontend..."
            self.frontend = Frontend(km)        
        
        
        def test_ipython_zmq_default_values(self):
            #Intial Values
            print >>sys.__stdout__,"TESTING DEFAULT VALUES"
            print >>sys.__stdout__,"KERNEL PID = ",self.frontend.kernel_pid    
            nt.assert_equals(self.frontend.kernel_pid,self.frontend.get_kernel_pid())
            print >>sys.__stdout__, "KERNEL/FRONTEND PROMPT = ",self.frontend.prompt_count
            nt.assert_equals(self.frontend.prompt_count,1)
        
        def test_request(self):
            #request
            code="print \"hello\""
            print >>sys.__stdout__,"TESTING REQUEST CODE = ",code
            reply_msg  = self.frontend.send_noninteractive_request(code)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            output_msg = self.frontend.recv_noninteractive_reply()
            nt.assert_equals(reply_msg['content']['status'],"ok")
            print >>sys.__stdout__,"STATUS = ",reply_msg['content']['status']
            nt.assert_equals(pyin_msg['content']['code'],code)
            print >>sys.__stdout__,"PYIN = ",pyin_msg['content']['code']
            nt.assert_equals(output_msg['content']['data'],"hello")
            print >>sys.__stdout__,"OUTPUT = ",output_msg['content']['data']
            
        def test_system_call(self):    
            #os system call
            code = "!echo 'hello'"
            print >> sys.__stdout__,"TESTING SYSTEM CALL CODE = ",code
            reply_msg  = self.frontend.send_noninteractive_request(code)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            output_msg = self.frontend.recv_noninteractive_reply()
            
            
            nt.assert_equals(reply_msg['content']['status'],"ok")
            nt.assert_equals(pyin_msg['content']['code'],code)
            nt.assert_equals(output_msg['content']['data'],"hello")
        
            
        def test_ctrl_c(self):
            self.code = ["for i in range(1000000):","    print i"]
            print >> sys.__stdout__,"TESTING CTRL+C FROM CODE = ",self.code
            thr = Thread(target=self.frontend.send_noninteractive_request,kwargs={"code":self.code})
            print >> sys.__stdout__,"INITIALIZING BUCLE"
            thr.start()
            time.sleep(1)
            
            print >> sys.__stdout__,"SENDING INTERRUPT"
            self.frontend.interrupt()
            time.sleep(1)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            
            nt.assert_equals(pyin_msg['content']['code'],self.code)
            print >>sys.__stdout__,"PYIN = ",pyin_msg['content']['code']
            
            while True:
                    err_msg = self.frontend.recv_noninteractive_reply()
                    try:
                        data=err_msg['content']['data']
                    except:
                        break
            #capture error output from kernel
            nt.assert_equals(err_msg['content']['status'],"error")
            print >>sys.__stdout__,"STATUS = ",err_msg['content']['status']
            
            nt.assert_equals(err_msg['content']['etype'],"<type 'exceptions.KeyboardInterrupt'>")
            print >>sys.__stdout__,"EXCEPTION TYPE = ",err_msg['content']['etype']
         
        def test_error_handler(self):
            code = "print a"    
            print >>sys.__stdout__,"TESTING ERROR IN REQUEST CODE = ",code
            reply_msg  = self.frontend.send_noninteractive_request(code)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            err_msg = self.frontend.recv_noninteractive_reply()
            
            nt.assert_equals(reply_msg['content']['status'],"error")
            print >>sys.__stdout__,"STATUS = ",err_msg['content']['status']
            
            nt.assert_equals(pyin_msg['content']['code'],code)
            print >>sys.__stdout__,"PYIN = ",pyin_msg['content']['code']
            
            nt.assert_equals(err_msg['content']['etype'],"<type 'exceptions.NameError'>")
            print >>sys.__stdout__,"EXCEPTION TYPE = ",err_msg['content']['etype']
            
            nt.assert_equals(err_msg['content']['evalue'],"name 'a' is not defined")
            print >>sys.__stdout__,"EXCEPTION VALUE = ",err_msg['content']['evalue']
        
        def test_completer(self):
            code = "import sys;import os;"    
            print >>sys.__stdout__,"TESTING COMPLETER = ",code
            self.frontend.runcode(code)
            reply_msg  = self.frontend.send_noninteractive_request(code)       
            nt.assert_equals(reply_msg['content']['status'],"ok")
            print >>sys.__stdout__,"STATUS = ",reply_msg['content']['status']
        
            code = "sys."
            print >>sys.__stdout__,"TESTING COMPLETER LINE = ",code
            matches = self.frontend.completer.request_completion(text=code)
            print >>sys.__stdout__,matches
        
        def tearDown(self):
            time.sleep(2)    
            self.frontend.kernel_stop()

            

        
