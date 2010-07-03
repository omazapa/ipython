# -*- coding: utf-8 -*-
from IPython.zmq.session import Session,  Message, msg_header, extract_header

def test_message():
    msg=Message({'msg_name':'test_message','content':'test_content'})
    msg_dict=msg.__dict__
    if msg != {'msg_name':'test_message','content':'test_content'}:
       raise ValueError("class Message can not change to dict")

def test_session():
    pass
    
def test_msg2obj():
    am = dict(x=1)
    ao = Message(am)
    assert ao.x == am['x']
            
    am['y'] = dict(z=1)
    ao = Message(am)
    assert ao.y.z == am['y']['z']
         
    k1, k2 = 'y', 'z'
    assert ao[k1][k2] == am[k1][k2]
          
    am2 = dict(ao)
    assert am['x'] == am2['x']
    assert am['y']['z'] == am2['y']['z']
    
    