import os, pyghidra
pyghidra.start()
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.app.cmd.disassemble import DisassembleCommand
from ghidra.app.cmd.function import CreateFunctionCmd

BASE = 0x100000
TARGETS = [0xC7E4DC, 0xC7E39C, 0x16B668]

def main():
    path = "/work/main.elf"
    with pyghidra.open_program(path, project_location="/tmp/ghproj",
                               project_name="sp2", analyze=False,
                               language="AARCH64:LE:64:v8A") as flat:
        prog = flat.getCurrentProgram()
        mon = ConsoleTaskMonitor()
        af = prog.getAddressFactory().getDefaultAddressSpace()
        fm = prog.getFunctionManager()
        from ghidra.app.decompiler import DecompInterface
        di = DecompInterface()
        di.openProgram(prog)
        for va in TARGETS:
            a = af.getAddress(va + BASE)
            print("=== %#x %s" % (va, prog.getSymbolTable().getPrimarySymbol(a)))
            cmd = DisassembleCommand(a, None, True)
            cmd.applyTo(prog, mon)
            fn = fm.getFunctionAt(a)
            if fn is None:
                cmd = CreateFunctionCmd(a)
                cmd.applyTo(prog, mon)
                fn = fm.getFunctionAt(a)
            if fn is None:
                print("no function")
                continue
            res = di.decompileFunction(fn, 60, mon)
            if res and res.decompileCompleted():
                print(res.getDecompiledFunction().getC())
            else:
                print("decompile failed", res.getErrorMessage() if res else None)

main()
