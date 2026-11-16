import pyghidra
pyghidra.start()
import jpype
for cls in ['ghidra.app.cmd.function.CreateFunctionCmd',
            'ghidra.app.cmd.disassemble.DisassembleCommand',
            'ghidra.app.util.demangler.DemanglerUtil']:
    C = jpype.JClass(cls)
    print('===', cls)
    for c in C.class_.getConstructors():
        print('  ', c)
    for m in C.class_.getMethods():
        if 'demangle' in m.getName() or 'Create' in m.getName():
            print('  M', m)
