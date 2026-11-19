#!/usr/bin/env python3
"""Decode the ObjectBox Model FlatBuffer emitted by the recovered schema builder."""
import json,struct,sys
from pathlib import Path

class Reader:
    def __init__(self,data):self.data=data
    def read(self,kind,offset):return struct.unpack_from('<'+kind,self.data,offset)[0]
    def field(self,table,slot):
        vt=table-self.read('i',table)
        if slot>=self.read('H',vt):return None
        offset=self.read('H',vt+slot);return table+offset if offset else None
    def number(self,table,slot,kind):
        pos=self.field(table,slot);return self.read(kind,pos) if pos is not None else 0
    def ptr(self,pos):return pos+self.read('I',pos)
    def string(self,table,slot):
        pos=self.field(table,slot)
        if pos is None:return None
        pos=self.ptr(pos);n=self.read('I',pos);return self.data[pos+4:pos+4+n].decode()
    def vector(self,table,slot):
        pos=self.field(table,slot)
        if pos is None:return []
        pos=self.ptr(pos)
        return [self.ptr(pos+4+4*i) for i in range(self.read('I',pos))]
    def iduid(self,table,slot):
        pos=self.field(table,slot)
        return {'id':self.read('I',pos),'uid':str(self.read('q',pos+8))} if pos is not None else None
    def model(self):
        m=self.ptr(0);entities=[]
        for ent in self.vector(m,10):
            props=[dict(name=self.string(p,6),identity=self.iduid(p,4),type=self.number(p,8,'H'),flags=self.number(p,10,'I'),
                        index=self.iduid(p,12),target=self.string(p,14),virtual_target=self.string(p,16)) for p in self.vector(ent,8)]
            relations=[dict(name=self.string(p,6),identity=self.iduid(p,4),target=self.iduid(p,8)) for p in self.vector(ent,12)]
            entities.append(dict(name=self.string(ent,6),identity=self.iduid(ent,4),last_property=self.iduid(ent,10),properties=props,relations=relations))
        return dict(name=self.string(m,6),model_version=self.number(m,4,'I'),version=self.number(m,8,'q'),last_entity=self.iduid(m,12),last_index=self.iduid(m,14),entities=entities)
if __name__=='__main__':print(json.dumps(Reader(Path(sys.argv[1]).read_bytes()).model(),ensure_ascii=False,indent=2))
