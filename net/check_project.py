import pyghidra
pyghidra.start()
proj = pyghidra.open_project("/tmp/ghproj/sp2", "sp2")
print("project", proj)
from ghidra.util.task import ConsoleTaskMonitor
mon = ConsoleTaskMonitor()
from ghidra.program.model.address import AddressSet
for f in proj.getProjectData().getRootFolder().getFiles():
    print("FILE", f.getPathname(), f.getName())
with pyghidra.program_context(proj, "/main.elf") as prog:
    st = prog.getSymbolTable()
    for va in [0x304E3C0, 0x2F6AB78, 0x304E3B8, 0x30C5700]:
        a = prog.getAddressFactory().getDefaultAddressSpace().getAddress(va)
        print(hex(va), "sym=", st.getPrimarySymbol(a), "insn=", prog.getListing().getInstructionAt(a))
    print("functions", prog.getFunctionManager().getFunctionCount())
proj.close()
