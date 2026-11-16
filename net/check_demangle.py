import pyghidra, re
pyghidra.start()
from ghidra.app.util.demangler import DemanglerUtil
proj = pyghidra.open_project("/tmp/ghproj/sp2", "sp2")
from ghidra.util.task import ConsoleTaskMonitor
mon = ConsoleTaskMonitor()
with pyghidra.program_context(proj, "/main.elf") as prog:
    af = prog.getAddressFactory().getDefaultAddressSpace()
    for va, nm in [(0xD7E39C, "_ZN2nn3pia3lan10InitializeEv"),
                   (0x126B668, "_ZN4Cnet17SystemCloneObjMgrC2Ev"),
                   (0x14B8E30, "_ZN2nn3pia4inet23NexCreateSessionSettingC1Ev")]:
        a = af.getAddress(va)
        print("addr", hex(va), "sym", prog.getSymbolTable().getPrimarySymbol(a))
        try:
            d = DemanglerUtil.demangle(prog, nm)
            print("  demangledName:", d.getDemangledName())
            print("  name:", d.getName())
            print("  ns:", d.getNamespace())
            print("  signature:", d.getSignature())
        except Exception as e:
            print("  err", e)
        f = prog.getFunctionManager().getFunctionAt(a)
        if f:
            print("  fn", f.getName(), "body", f.getBody().getNumAddresses())
proj.close()
