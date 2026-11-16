import inspect, pyghidra
pyghidra.start()
from ghidra.app.script import GhidraScriptUtil
from ghidra.program.flatapi import FlatProgramAPI
from ghidra.app.cmd.disassemble import DisassembleCommand
from ghidra.app.cmd.function import CreateFunctionCmd
print("DisassembleCommand", inspect.signature(DisassembleCommand))
print("CreateFunctionCmd", [m for m in dir(CreateFunctionCmd) if 'Create' in m][:10])
print("FlatAPI createFunction", inspect.signature(FlatProgramAPI.createFunction))
EOF_MARKER = None
