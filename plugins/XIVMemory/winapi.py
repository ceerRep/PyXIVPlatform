#! /usr/bin/env python3

from ctypes import *
from typing import *


__all__ = ["Winapi"]


class _WINAPI:
    class ModuleInfo(Structure):
        _fields_ = [
            ("lpBaseOfDll", c_void_p),
            ("SizeOfImage", c_uint32),
            ("EntryPoint", c_void_p)
        ]

    PROCESS_VM_OPERATION = 0x08
    PROCESS_VM_READ = 0x10
    PROCESS_VM_WRITE = 0x20
    PROCESS_QUERY_INFORMATION = 0x400

    OpenProcess = windll.kernel32.OpenProcess
    OpenProcess.argtypes = [c_uint32, c_uint32, c_uint32]
    OpenProcess.restype = c_void_p  # HANDLE

    CloseHandle = windll.kernel32.CloseHandle
    CloseHandle.argtypes = [c_void_p]

    ReadProcessMemory = windll.kernel32.ReadProcessMemory
    ReadProcessMemory.restype = c_int32
    ReadProcessMemory.argtypes = [
        c_void_p,
        c_void_p,
        c_char_p,
        c_uint64,
        POINTER(c_uint64)]

    EnumProcessModules = windll.psapi.EnumProcessModules
    EnumProcessModules.restype = c_uint32
    EnumProcessModules.argtypes = [c_void_p,
                                   POINTER(c_void_p),
                                   c_uint32,
                                   POINTER(c_uint32)]

    GetModuleInformation = windll.psapi.GetModuleInformation
    GetModuleInformation.restype = c_uint32
    GetModuleInformation.argtypes = [
        c_void_p, c_void_p, POINTER(ModuleInfo), c_uint32]

    GetModuleFileNameExW = windll.psapi.GetModuleFileNameExW
    GetModuleFileNameExW.restype = c_uint32
    GetModuleFileNameExW.argtypes = [c_void_p, c_void_p, c_wchar_p, c_uint32]

    FindWindowW = windll.user32.FindWindowW
    FindWindowW.restype = c_void_p  # HWND
    FindWindowW.argtypes = [c_wchar_p, c_wchar_p]

    FindWindowExW = windll.user32.FindWindowExW
    FindWindowExW.restype = c_void_p # HWND
    FindWindowExW.argtypes = [c_void_p, c_void_p, c_wchar_p, c_wchar_p]

    GetWindowThreadProcessId = windll.user32.GetWindowThreadProcessId
    GetWindowThreadProcessId.restype = c_uint32
    GetWindowThreadProcessId.argtypes = [c_void_p, POINTER(c_uint32)]

    SendMessageW = windll.user32.SendMessageW
    SendMessageW.argtypes = [c_void_p, c_uint32, c_uint64, c_uint64]


class Winapi:
    @staticmethod
    def open_process(pid: int) -> int:
        return _WINAPI.OpenProcess(
            _WINAPI.PROCESS_QUERY_INFORMATION | _WINAPI.PROCESS_VM_OPERATION | _WINAPI.PROCESS_VM_READ | _WINAPI.PROCESS_VM_WRITE,
            False,
            pid
        )

    @staticmethod
    def close_handle(handle: int) -> int:
        return _WINAPI.CloseHandle(handle)

    @staticmethod
    def read_process_memory(handle: int, address: int, size: int) -> bytearray:
        buffer = bytearray(size)

        bytes_read = c_uint64()

        success = _WINAPI.ReadProcessMemory(
            handle,
            c_void_p(address),
            (c_char * size).from_buffer(buffer),
            size,
            byref(bytes_read)
        )

        if not success:
            return bytearray()

        return buffer

    @staticmethod
    def enum_process_modules(handle: int) -> List[Tuple[str, int]]:
        ret = []

        needed = c_uint32()
        modules = (c_void_p * 512)()

        while True:
            if _WINAPI.EnumProcessModules(handle, modules, len(modules), byref(needed)) == 0:
                return []

            if needed.value <= len(modules):
                modules = modules[:needed.value]
                break

            modules = (c_void_p * needed.value)()

        for module in modules:
            info = _WINAPI.ModuleInfo()
            buffer = create_unicode_buffer(512)
            _WINAPI.GetModuleFileNameExW(handle, module, buffer, 512)
            name: str = buffer.value
            _WINAPI.GetModuleInformation(
                handle, module, byref(info), sizeof(_WINAPI.ModuleInfo))
            ret.append((name, info.lpBaseOfDll))

        return ret
    
    @staticmethod
    def get_module_base_address(handle: int, name: str):
        needed = c_uint32()
        modules = (c_void_p * 512)()

        if _WINAPI.EnumProcessModules(handle, modules, 512, byref(needed)) == 0:
            return 0

        for module in modules:
            info = _WINAPI.ModuleInfo()
            buffer = create_unicode_buffer(512)
            _WINAPI.GetModuleFileNameExW(handle, module, buffer, 512)
            name: str = buffer.value
            if name.endswith("ffxiv_dx11.exe"):
                _WINAPI.GetModuleInformation(handle, module, byref(info), sizeof(_WINAPI.ModuleInfo))
                return info.lpBaseOfDll
        return 0

    @staticmethod
    def find_window(window_class: Optional[str], window_name: Optional[str]) -> int:
        return _WINAPI.FindWindowW(window_class, window_name)
    
    @staticmethod
    def find_window_ex(window_parent: Optional[int], window_after: Optional[int], window_class: Optional[str], window_name: Optional[str]) -> int:
        return _WINAPI.FindWindowExW(window_parent, window_after, window_class, window_name)

    @staticmethod
    def get_window_pid(hwnd: int) -> int:
        pid = c_uint32()
        _WINAPI.GetWindowThreadProcessId(hwnd, byref(pid))

        return pid

    @staticmethod
    def send_message(hwnd: int, msg: int, wparam: int, lparam: int):
        _WINAPI.SendMessageW(hwnd, msg, wparam, lparam)
