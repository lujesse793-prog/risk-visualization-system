import os,sys
d = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(d, chr(115)+chr(101)+chr(114)+chr(118)+chr(101)+chr(114), chr(97)+chr(112)+chr(112)+chr(46)+chr(112)+chr(121))
with open(p, chr(114), encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)) as f: c = f.read()
# Replace the broken handler
old = chr(100)+chr(101)+chr(102)+chr(32)+chr(97)+chr(100)+chr(100)+chr(95)+chr(99)+chr(104)+chr(97)+chr(114)+chr(115)+chr(101)+chr(116)+chr(40)+chr(114)+chr(101)+chr(115)+chr(112)+chr(111)+chr(110)+chr(115)+chr(101)+chr(41)+chr(58)
new = chr(100)+chr(101)+chr(102)+chr(32)+chr(97)+chr(100)+chr(100)+chr(95)+chr(99)+chr(104)+chr(97)+chr(114)+chr(115)+chr(101)+chr(116)+chr(40)+chr(114)+chr(101)+chr(115)+chr(112)+chr(111)+chr(110)+chr(115)+chr(101)+chr(41)+chr(58)
c = c.replace(old, new)
with open(p, chr(119), encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)) as f: f.write(c)
print(chr(79)+chr(75))
