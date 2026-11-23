"""Build Inksplash2 on Windows using the generated objects from the null build."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


RUNTIME = Path(__file__).resolve().parents[1] / "baseline/totk-recomp/runtime"
SYSTEM_LIBRARIES = (
    "winmm", "ole32", "uuid", "mfplat", "mf", "mfuuid", "propsys", "psapi", "gdi32",
)


def require_file(path):
    if not path.is_file():
        raise SystemExit(f"Missing file: {path}")
    return path


def generated_objects(data, cache):
    # Preserve the validated mix of -O0 and -O1 objects. The all-O0 build
    # produces a PE image too large for the Windows loader.
    compact = {path.name.removeprefix("compact-") for path in cache.glob("compact-tu_*.o")}
    if len(compact) != 24:
        raise SystemExit(f"Expected the 24 compact main objects in {cache}, found {len(compact)}")
    for group in ("patched", "sdk"):
        directory = data / f"gen-ink-{group}"
        units = sorted(directory.glob("*.cpp"))
        if not units:
            raise SystemExit(f"No generated C++ files in {directory}")
        if group == "patched" and not compact <= {unit.with_suffix(".o").name for unit in units}:
            raise SystemExit(f"The compact objects do not match the generated sources in {directory}")
        for unit in units:
            name = unit.with_suffix(".o").name
            prefix = "compact" if group == "patched" and name in compact else group
            obj = require_file(cache / f"{prefix}-{name}")
            if obj.stat().st_mtime_ns < unit.stat().st_mtime_ns:
                raise SystemExit(f"Generated object is older than its source: {obj}")
            yield obj


def sdk_files(sdk):
    include = sdk / "Include"
    for header in ("vulkan/vulkan.h", "vulkan/vulkan_core.h", "shaderc/shaderc.h"):
        require_file(include / header)
    libraries = [require_file(sdk / "Lib" / name) for name in ("vulkan-1.lib", "shaderc_shared.lib")]
    return [include], libraries, require_file(sdk / "Bin/shaderc_shared.dll")


def import_library(dll, output):
    exports = subprocess.check_output(["llvm-readobj", "--coff-exports", str(dll)], text=True)
    names = re.findall(r"^\s+Name: ([A-Za-z_][A-Za-z_0-9]*)$", exports, re.MULTILINE)
    if not names:
        raise SystemExit(f"No named exports found in {dll}")
    definition = output / f"{dll.stem}.def"
    definition.write_text(f"LIBRARY {dll.name}\nEXPORTS\n" + "\n".join(names) + "\n", encoding="ascii")
    archive = output / f"lib{dll.stem}.dll.a"
    subprocess.run(["llvm-dlltool", "-m", "i386:x86-64", "-d", str(definition), "-l", str(archive)], check=True)
    return archive


def vulkan_files(args, output):
    if args.vulkan_headers or args.shaderc_headers or args.shaderc_dll:
        if not (args.vulkan_headers and args.shaderc_headers and args.shaderc_dll):
            raise SystemExit("Pass --vulkan-headers, --shaderc-headers and --shaderc-dll together.")
        vk_headers = args.vulkan_headers.resolve()
        shaderc_headers = args.shaderc_headers.resolve()
        shaderc = require_file(args.shaderc_dll.resolve())
        require_file(shaderc_headers / "shaderc/shaderc.h")
        loader = require_file(Path(os.environ["SystemRoot"]) / "System32/vulkan-1.dll")
        output.mkdir(parents=True, exist_ok=True)
        libraries = [import_library(dll, output) for dll in (loader, shaderc)]
        includes = [vk_headers, shaderc_headers]
    elif args.vulkan_sdk:
        includes, libraries, shaderc = sdk_files(args.vulkan_sdk.resolve())
    else:
        raise SystemExit("Set VULKAN_SDK, pass --vulkan-sdk, or pass separate headers and shaderc DLL.")
    vk_core = require_file(includes[0] / "vulkan/vulkan_core.h")
    if "VK_KHR_unified_image_layouts" not in vk_core.read_text(encoding="utf-8"):
        raise SystemExit(f"Vulkan headers are too old in {vk_core.parent}")
    return includes, libraries, shaderc


def write_launcher(output, data, backend):
    runner = Path(__file__).with_name("run-windows.cmd").resolve()
    launcher = output / f"run-sp2-ink-{backend}.cmd"
    launcher.write_text(
        '@echo off\n'
        f'call "{runner}" "{data}" "%~dp0sp2-ink-{backend}.exe" {backend}\n'
        'exit /b %ERRORLEVEL%\n',
        encoding="utf-8",
    )
    print(f"Launcher: {launcher}", flush=True)


def build(args):
    clang = shutil.which("clang")
    clangxx = shutil.which("clang++")
    if not clang or not clangxx:
        raise SystemExit("Put the x64 WinLibs Clang toolchain on PATH.")
    if subprocess.check_output([clangxx, "-dumpmachine"], text=True).strip() != "x86_64-w64-windows-gnu":
        raise SystemExit("This build requires Clang targeting x86_64-w64-windows-gnu.")
    winpthread = require_file(Path(clangxx).resolve().with_name("libwinpthread-1.dll"))

    output = args.output.resolve()
    data = args.data.resolve()
    generated = list(generated_objects(data, data / "win-null/obj"))
    opus = require_file(data / "win-opus-build/libopus.a")
    runtime_sources = list(sorted(RUNTIME.glob("*.cpp")))
    nvn = RUNTIME / "nvn"
    nvn_sources = list(sorted(nvn.glob("*.c")))
    backend_sources = []
    backend_flags = []
    backend_libraries = []
    shaderc = None
    if args.backend == "null":
        nvn_sources.append(RUNTIME / "linux/null_stubs.c")
    else:
        includes, backend_libraries, shaderc = vulkan_files(args, output)
        nvn_sources.remove(nvn / "backend_null.c")
        backend_sources = sorted(nvn.glob("vulkan/*.c")) + sorted(nvn.glob("maxwell/*.c"))
        backend_flags = [
            "-D_WIN32_WINNT=0x0A00", "-I", str(nvn / "shim"),
            *(flag for path in includes for flag in ("-I", str(path))),
            "-include", str(nvn / "shim/compat.h"),
        ]

    obj_dir = output / "obj"
    obj_dir.mkdir(parents=True, exist_ok=True)
    common = ["-O1", "-maes", "-msse4.2", "-g0", "-I", str(RUNTIME), "-I", str(nvn)]

    def compile_source(source):
        obj = obj_dir / ("-".join(source.relative_to(RUNTIME).with_suffix(".o").parts))
        if source.suffix == ".cpp":
            compiler = [clangxx, "-std=c++20", "-femulated-tls"]
        else:
            compiler = [clang, "-std=gnu17"]
        flags = backend_flags if source in backend_sources else []
        subprocess.run([*compiler, *common, *flags, "-c", str(source), "-o", str(obj)], check=True)
        return obj

    print(f"Reusing {len(generated)} generated objects. Building {args.backend} runtime.", flush=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        runtime_objects = list(pool.map(compile_source, runtime_sources + nvn_sources + backend_sources))

    rsp = output / "inputs.rsp"
    inputs = [*runtime_objects, *generated, opus, *backend_libraries]
    rsp.write_text("".join(f'"{path.as_posix()}"\n' for path in inputs), encoding="utf-8")
    executable = output / f"sp2-ink-{args.backend}.exe"
    temporary = output / f"{executable.stem}.{os.getpid()}.exe"
    subprocess.run([
        clangxx, f"@{rsp}", "-fuse-ld=lld", "-Wl,--stack,67108864",
        "-static-libstdc++", "-static-libgcc", "-pthread", "-lwinpthread",
        *(f"-l{lib}" for lib in SYSTEM_LIBRARIES), "-o", str(temporary),
    ], check=True)
    for dll in [winpthread, *([shaderc] if shaderc is not None else [])]:
        if dll != output / dll.name:
            shutil.copy2(dll, output / dll.name)
    os.replace(temporary, executable)
    print(f"Linked {executable}", flush=True)
    write_launcher(output, data, args.backend)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="Local data and build directory (eur-recomp)")
    parser.add_argument("--backend", choices=("vulkan", "null"), default="vulkan")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vulkan-sdk", type=Path, default=os.environ.get("VULKAN_SDK"))
    parser.add_argument("--vulkan-headers", type=Path, help="Directory containing vulkan/vulkan.h")
    parser.add_argument("--shaderc-headers", type=Path, help="Directory containing shaderc/shaderc.h")
    parser.add_argument("--shaderc-dll", type=Path, help="Path to a compatible x64 shaderc shared DLL")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This build runs on native Windows.")
    if args.jobs < 1:
        parser.error("--jobs must be positive.")
    build(args)


if __name__ == "__main__":
    main()
