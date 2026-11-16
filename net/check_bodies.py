import pyghidra
pyghidra.start()
proj = pyghidra.open_project("/tmp/ghproj/sp2", "sp2")
from ghidra.util.task import ConsoleTaskMonitor
mon = ConsoleTaskMonitor()
with pyghidra.program_context(proj, "/main.elf") as prog:
    af = prog.getAddressFactory().getDefaultAddressSpace()
    for va in [0xD7E39C, 0x116B668, 0x116B760]:
        a = af.getAddress(va)
        f = prog.getFunctionManager().getFunctionAt(a)
        print(hex(va), "sym", prog.getSymbolTable().getPrimarySymbol(a), "fn", f)
        if f:
            b = f.getBody()
            print("  body", b.getMinAddress(), b.getMaxAddress(), "num", b.getNumAddresses())
            ins = prog.getListing().getInstructions(b, True)
            n = 0
            for i in ins:
                n += 1
            print("  insns", n)
            print("  first", prog.getListing().getInstructionAt(a))
proj.close()
