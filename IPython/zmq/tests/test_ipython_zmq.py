# -*- coding: utf-8 -*-
"""Frontend of ipython working with python-zmq

Ipython's frontend, is a ipython interface that send request to kernel and proccess the kernel's outputs.

For more details, see the ipython-zmq design
"""
#-----------------------------------------------------------------------------
# Copyright (C) 2010 The IPython Development Team
#
# Distributed under the terms of the BSD License. The full license is in
# the file COPYING, distributed as part of this software.
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

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
        """ class that test kernel and frontend methods, 
        init kernel in a separate process using launch_kernel and 
        create a noninteractive frontend
        """
        def setUp(self):
            """Init frontend and kernel each test's method
            """
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
            """ Read default values loaded in frontend in the begin
            """
            #Intial Values
            print >>sys.__stdout__,"TESTING DEFAULT VALUES"
            print >>sys.__stdout__,"KERNEL PID = ",self.frontend.kernel_pid    
            nt.assert_equals(self.frontend.kernel_pid,self.frontend.get_kernel_pid())
            print >>sys.__stdout__, "KERNEL/FRONTEND PROMPT = ",self.frontend.prompt_count
            nt.assert_equals(self.frontend.prompt_count,1)
        
        def test_request(self):
            """Test a simple request code and get outputs to compare
            """
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
            """request that use alias! to make a system call with a subprocess
               and try capture pipe output
            """
            #os system call
            code = "!echo 'hello'"
            print >> sys.__stdout__,"TESTING SYSTEM CALL CODE = ",code
            reply_msg  = self.frontend.send_noninteractive_request(code)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            output_msg = self.frontend.recv_noninteractive_reply()
            
            
            nt.assert_equals(reply_msg['content']['status'],"ok")
            print >>sys.__stdout__,"STATUS = ",reply_msg['content']['status']
            nt.assert_equals(pyin_msg['content']['code'],code)
            print >>sys.__stdout__,"PYIN = ",pyin_msg['content']['code']
            nt.assert_equals(output_msg['content']['data'],"hello")
            print >>sys.__stdout__,"OUTPUT = ",output_msg['content']['data']
            
        def test_ctrl_c(self):
            """ Method that call a large blucle code, to send signal SIGINT using
                interrupt from frontend and to capture KeyboardInterrupt 
            """
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
            
            #read print output before interrupt
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
            """ send a code 'print a' where a is not defined in kernel and captured
            <type 'exceptions.NameError'> where name 'a' is not defined
            """
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
            """ send a tab-completion request to complete code from kernel
            """
            code_import = "import sys"    
            print >>sys.__stdout__,"TESTING COMPLETER = ",code_import
            self.frontend.runcode(code_import)
            reply_msg  = self.frontend.send_noninteractive_request(code_import)       
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            
            nt.assert_equals(reply_msg['content']['status'],"ok")
            print >>sys.__stdout__,"STATUS = ",reply_msg['content']['status']
            nt.assert_equals(pyin_msg['content']['code'],code_import)
            print >>sys.__stdout__,"PYIN = ",pyin_msg['content']['code']
            
            text = ["sys."]
            print >>sys.__stdout__,"TESTING COMPLETER LINE = ",text
            matches = self.frontend.completer.request_completion(text=text)
            #matches = self.frontend.completer(text=text,state=0)
            print >>sys.__stdout__,matches
        
        def test_indexed_output(self):
            """test index output in kernel to call index with underline 
            and number like mathematica's style
            """
            code = "1234"
            print >> sys.__stdout__,"TESTING INDEXED OUTPUT SENDING CODE = ",code
            reply_msg  = self.frontend.send_noninteractive_request(code)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            output_msg = self.frontend.recv_noninteractive_reply()
            
            
            nt.assert_equals(reply_msg['content']['status'],"ok")
            print >>sys.__stdout__,"STATUS = ",reply_msg['content']['status']
            nt.assert_equals(pyin_msg['content']['code'],code)
            print >>sys.__stdout__,"PYIN = ",pyin_msg['content']['code']
            nt.assert_equals(output_msg['content']['data'],"1234")
            print >>sys.__stdout__,"OUTPUT = ",output_msg['content']['data']
            
            code = "print _1"
            print >> sys.__stdout__,"TESTING INDEXED OUTPUT SENDING UNDERLINE CODE = ",code
            reply_msg  = self.frontend.send_noninteractive_request(code)
            pyin_msg   = self.frontend.recv_noninteractive_reply()
            output_msg = self.frontend.recv_noninteractive_reply()
            
            
            nt.assert_equals(reply_msg['content']['status'],"ok")
            print >>sys.__stdout__,"STATUS = ",reply_msg['content']['status']
            nt.assert_equals(pyin_msg['content']['code'],code)
            print >>sys.__stdout__,"PYIN = ",pyin_msg['content']['code']
            nt.assert_equals(output_msg['content']['data'],"1234")
            print >>sys.__stdout__,"OUTPUT = ",output_msg['content']['data']
            
                
        
        def tearDown(self):
            """ stop kernel after an execution
            """
            time.sleep(2)    
            self.frontend.kernel_stop()

            

        
