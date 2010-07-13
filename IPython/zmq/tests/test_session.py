# -*- coding: utf-8 -*-
import nose.tools as nt
from IPython.zmq.session import Session,  Message, msg_header, extract_header
from IPython.testing import decorators as dec

def test_message():
    msg = Message({'msg_name':'test_message','content':'test_content'})
    msg_dict = msg.__dict__
    msg_str = msg.__str__()
    msg_expected = {'msg_name':'test_message','content':'test_content'}
    nt.assert_equals(msg_dict, msg_expected,
                     "class Message can not change to dict")
	

@dec.parametric
def test_session():
    session = Session()
    msg_header = session.msg_header()
    for key in ['msg_id', 'session', 'username']:
        yield nt.assert_true(key in msg_header)
    
    
@dec.parametric
def test_msg2obj():
    am = dict(x=1)
    ao = Message(am)
    nt.assert_equals(ao.x, am['x'])
            
    am['y'] = dict(z=1)
    ao = Message(am)
    nt.assert_equals(ao.y.z,am['y']['z'])
         
    k1, k2 = 'y', 'z'
    nt.assert_equals(ao[k1][k2], am[k1][k2])
          
    am2 = dict(ao)
    nt.assert_equals(am['x'], am2['x'])
    nt.assert_equals(am['y']['z'], am2['y']['z'])
    
    
