import pyghidra, inspect
print([x for x in dir(pyghidra) if not x.startswith('_')])
for n in ['open_project','program_context','program_loader','open_program']:
    o=getattr(pyghidra,n,None)
    if o: print('===',n, inspect.signature(o)); print(inspect.getdoc(o)[:800])
