# -*- coding: utf-8 -*-
"""
============================================================================
 Terraria 自动钓鱼机器人 v1.1（多语言版 · Python 实现）
 Terraria Auto Fishing Bot (Multilingual UI, Python + ctypes)
============================================================================

 参考项目 : Izzy's Fishing Bot v2.00（作者 D.RU$$ / RussDev7）
 作者 :PPLLAAS258 原作者:lzzy
 工作原理（与原版一致，100% 外部操作，不读写游戏内存）:
     1. 通过 Windows CoreAudio (WASAPI) 枚举默认扬声器上的全部音频会话；
     2. 找到属于目标进程（默认 Terraria / tModLoader / javaw）的音频轨道，
        读取其峰值音量（VU 值）；
     3. 当 VU 超过灵敏度阈值（鱼“咬钩”的音效）时，
        模拟鼠标左键点击收线，等待片刻后再次点击重新抛竿，循环往复；
     4. 只用声音驱动 + 鼠标宏，无内存读写，不需要开机自启动。

 支持语言 : 英语/德语/意大利语/法语/西班牙语/俄语/简体中文/巴西葡萄牙语/
            波兰语/日语/朝鲜语/繁体中文（点击界面 Language 按钮切换）
 依赖     : 仅 Python 标准库（tkinter + ctypes），无需安装任何第三方包。
 配置文件 : 同目录 TerrariaAutoFishPy.ini
============================================================================
"""

import ctypes
import configparser
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox, scrolledtext
from ctypes import (wintypes, WINFUNCTYPE, POINTER, Structure, byref,
                    c_void_p, c_ulong, c_uint, c_int, c_long, c_float,
                    c_ushort, c_ubyte, c_uint32, c_longlong, c_size_t,
                    c_wchar, c_wchar_p, cast)

# ============================================================================
# 一、CoreAudio (WASAPI) COM 接口 —— ctypes 手工声明
# ============================================================================

HRESULT = c_long
CLSCTX_ALL = 0x17
STDMETHODCALLTYPE = WINFUNCTYPE

class GUID(Structure):
    _fields_ = [("Data1", c_uint32),
                ("Data2", c_ushort),
                ("Data3", c_ushort),
                ("Data4", c_ubyte * 8)]

def make_guid(l, w1, w2, b):
    g = GUID()
    g.Data1 = l; g.Data2 = w1; g.Data3 = w2
    for i, x in enumerate(b):
        g.Data4[i] = x
    return g

CLSID_MMDeviceEnumerator   = make_guid(0xBCDE0395, 0xE52F, 0x467C, [0x8E,0x3D,0xC4,0x57,0x92,0x91,0x69,0x2E])
IID_IMMDeviceEnumerator    = make_guid(0xA95664D2, 0x9614, 0x4F35, [0xA7,0x46,0xDE,0x8D,0xB6,0x36,0x17,0xE6])
IID_IAudioSessionManager2  = make_guid(0x77AA99A0, 0x1BD6, 0x484F, [0x8B,0xC7,0x2C,0x65,0x4C,0x9A,0x9B,0x6F])
IID_IAudioSessionControl2  = make_guid(0xBFB7FF88, 0x7239, 0x4FC9, [0x8F,0xA2,0x07,0xC9,0x50,0xBE,0x9C,0x6D])
IID_IAudioMeterInformation = make_guid(0xC02216F6, 0x8C67, 0x4B5B, [0x9D,0x00,0xD0,0x08,0xE7,0x3E,0x00,0x64])

class IUnknown(Structure): pass
class IUnknownVtbl(Structure):
    _fields_ = [
        ("QueryInterface", STDMETHODCALLTYPE(HRESULT, POINTER(IUnknown), POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Release",        STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
    ]
IUnknown._fields_ = [("lpVtbl", POINTER(IUnknownVtbl))]

class IMMDeviceEnumerator(Structure): pass
class IMMDeviceEnumeratorVtbl(Structure):
    _fields_ = [
        ("QueryInterface", STDMETHODCALLTYPE(HRESULT, POINTER(IUnknown), POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Release",        STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("EnumAudioEndpoints",            STDMETHODCALLTYPE(HRESULT, POINTER(IMMDeviceEnumerator), c_int, c_uint, POINTER(c_void_p))),
        ("GetDefaultAudioEndpoint",       STDMETHODCALLTYPE(HRESULT, POINTER(IMMDeviceEnumerator), c_int, c_int, POINTER(c_void_p))),
        ("GetDevice",                     STDMETHODCALLTYPE(HRESULT, POINTER(IMMDeviceEnumerator), c_wchar_p, POINTER(c_void_p))),
        ("RegisterEndpointNotificationCallback",   STDMETHODCALLTYPE(HRESULT, POINTER(IMMDeviceEnumerator), c_void_p)),
        ("UnregisterEndpointNotificationCallback", STDMETHODCALLTYPE(HRESULT, POINTER(IMMDeviceEnumerator), c_void_p)),
    ]
IMMDeviceEnumerator._fields_ = [("lpVtbl", POINTER(IMMDeviceEnumeratorVtbl))]

class IMMDevice(Structure): pass
class IMMDeviceVtbl(Structure):
    _fields_ = [
        ("QueryInterface", STDMETHODCALLTYPE(HRESULT, POINTER(IUnknown), POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Release",        STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Activate",           STDMETHODCALLTYPE(HRESULT, POINTER(IMMDevice), POINTER(GUID), c_uint, c_void_p, POINTER(c_void_p))),
        ("OpenPropertyStore",  STDMETHODCALLTYPE(HRESULT, POINTER(IMMDevice), c_uint, POINTER(c_void_p))),
        ("GetId",              STDMETHODCALLTYPE(HRESULT, POINTER(IMMDevice), POINTER(c_wchar_p))),
        ("GetState",           STDMETHODCALLTYPE(HRESULT, POINTER(IMMDevice), POINTER(c_uint))),
    ]
IMMDevice._fields_ = [("lpVtbl", POINTER(IMMDeviceVtbl))]

class IAudioSessionManager2(Structure): pass
class IAudioSessionManager2Vtbl(Structure):
    _fields_ = [
        ("QueryInterface", STDMETHODCALLTYPE(HRESULT, POINTER(IUnknown), POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Release",        STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("GetAudioSessionControl",        STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionManager2), POINTER(GUID), c_uint, POINTER(c_void_p))),
        ("GetSimpleAudioVolume",          STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionManager2), POINTER(GUID), c_uint, POINTER(c_void_p))),
        ("GetSessionEnumerator",          STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionManager2), POINTER(c_void_p))),
        ("RegisterSessionNotification",   STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionManager2), c_void_p)),
        ("UnregisterSessionNotification", STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionManager2), c_void_p)),
        ("RegisterDuckNotification",      STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionManager2), c_wchar_p, c_void_p)),
        ("UnregisterDuckNotification",    STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionManager2), c_void_p)),
    ]
IAudioSessionManager2._fields_ = [("lpVtbl", POINTER(IAudioSessionManager2Vtbl))]

class IAudioSessionEnumerator(Structure): pass
class IAudioSessionEnumeratorVtbl(Structure):
    _fields_ = [
        ("QueryInterface", STDMETHODCALLTYPE(HRESULT, POINTER(IUnknown), POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Release",        STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("GetCount",       STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionEnumerator), POINTER(c_int))),
        ("GetSession",     STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionEnumerator), c_int, POINTER(c_void_p))),
    ]
IAudioSessionEnumerator._fields_ = [("lpVtbl", POINTER(IAudioSessionEnumeratorVtbl))]

class IAudioSessionControl2(Structure): pass
class IAudioSessionControl2Vtbl(Structure):
    _fields_ = [
        ("QueryInterface", STDMETHODCALLTYPE(HRESULT, POINTER(IUnknown), POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Release",        STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("GetState",                     STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), POINTER(c_int))),
        ("GetDisplayName",               STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), POINTER(c_wchar_p))),
        ("SetDisplayName",               STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), c_wchar_p, POINTER(GUID))),
        ("GetIconPath",                  STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), POINTER(c_wchar_p))),
        ("SetIconPath",                  STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), c_wchar_p, POINTER(GUID))),
        ("GetGroupingParam",             STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), POINTER(GUID))),
        ("SetGroupingParam",             STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), POINTER(GUID), POINTER(GUID))),
        ("RegisterAudioSessionNotification",   STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), c_void_p)),
        ("UnregisterAudioSessionNotification", STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), c_void_p)),
        ("GetSessionIdentifier",         STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), POINTER(c_wchar_p))),
        ("GetSessionInstanceIdentifier", STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), POINTER(c_wchar_p))),
        ("GetProcessId",                 STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), POINTER(c_uint32))),
        ("IsSystemSoundsSession",        STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2))),
        ("SetDuckingPreference",         STDMETHODCALLTYPE(HRESULT, POINTER(IAudioSessionControl2), c_int)),
    ]
IAudioSessionControl2._fields_ = [("lpVtbl", POINTER(IAudioSessionControl2Vtbl))]

class IAudioMeterInformation(Structure): pass
class IAudioMeterInformationVtbl(Structure):
    _fields_ = [
        ("QueryInterface", STDMETHODCALLTYPE(HRESULT, POINTER(IUnknown), POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Release",        STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("GetPeakValue",           STDMETHODCALLTYPE(HRESULT, POINTER(IAudioMeterInformation), POINTER(c_float))),
        ("GetMeteringChannelCount",STDMETHODCALLTYPE(HRESULT, POINTER(IAudioMeterInformation), POINTER(c_uint))),
        ("GetChannelsPeakValues",  STDMETHODCALLTYPE(HRESULT, POINTER(IAudioMeterInformation), c_uint, POINTER(c_float))),
        ("QueryHardwareSupport",   STDMETHODCALLTYPE(HRESULT, POINTER(IAudioMeterInformation), POINTER(c_uint))),
    ]
IAudioMeterInformation._fields_ = [("lpVtbl", POINTER(IAudioMeterInformationVtbl))]

class IMMDeviceCollection(Structure): pass
class IMMDeviceCollectionVtbl(Structure):
    _fields_ = [
        ("QueryInterface", STDMETHODCALLTYPE(HRESULT, POINTER(IUnknown), POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("Release",        STDMETHODCALLTYPE(c_ulong, POINTER(IUnknown))),
        ("GetCount",       STDMETHODCALLTYPE(HRESULT, POINTER(IMMDeviceCollection), POINTER(c_uint))),
        ("Item",           STDMETHODCALLTYPE(HRESULT, POINTER(IMMDeviceCollection), c_uint, POINTER(c_void_p))),
    ]
IMMDeviceCollection._fields_ = [("lpVtbl", POINTER(IMMDeviceCollectionVtbl))]

# ============================================================================
# 二、Win32 API 声明
# ============================================================================

ole32   = ctypes.oledll.ole32
user32  = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi   = ctypes.windll.psapi
gdi32   = ctypes.windll.gdi32

ole32.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, c_ulong, POINTER(GUID), POINTER(c_void_p)]
ole32.CoCreateInstance.restype  = HRESULT
ole32.CoInitializeEx.argtypes   = [c_void_p, c_ulong]
ole32.CoInitializeEx.restype    = HRESULT
ole32.CoUninitialize.argtypes   = []

user32.mouse_event.argtypes = [c_uint, c_uint, c_uint, c_uint, c_ulong]
user32.mouse_event.restype  = None

kernel32.CreateToolhelp32Snapshot.argtypes = [c_uint, c_uint]
kernel32.CreateToolhelp32Snapshot.restype  = c_void_p
kernel32.CloseHandle.argtypes = [c_void_p]
kernel32.CloseHandle.restype  = c_int
kernel32.OpenProcess.argtypes = [c_uint, c_int, c_uint]
kernel32.OpenProcess.restype  = c_void_p
psapi.GetModuleBaseNameW.argtypes = [c_void_p, c_void_p, c_wchar_p, c_uint]
psapi.GetModuleBaseNameW.restype  = c_uint

user32.RegisterHotKey.argtypes = [c_void_p, c_int, c_uint, c_uint]
user32.RegisterHotKey.restype  = c_int
user32.UnregisterHotKey.argtypes = [c_void_p, c_int]
user32.UnregisterHotKey.restype  = c_int

user32.GetDC.argtypes = [c_void_p]
user32.GetDC.restype  = c_void_p
user32.ReleaseDC.argtypes = [c_void_p, c_void_p]
user32.ReleaseDC.restype  = c_int
gdi32.GetDeviceCaps.argtypes = [c_void_p, c_int]
gdi32.GetDeviceCaps.restype  = c_int

class PROCESSENTRY32W(Structure):
    _fields_ = [("dwSize", c_uint32),
                ("cntUsage", c_uint32),
                ("th32ProcessID", c_uint32),
                ("th32DefaultHeapID", POINTER(c_ulong)),
                ("th32ModuleID", c_uint32),
                ("cntThreads", c_uint32),
                ("th32ParentProcessID", c_uint32),
                ("pcPriClassBase", c_long),
                ("dwFlags", c_uint32),
                ("szExeFile", c_wchar * 260)]
kernel32.Process32FirstW.argtypes = [c_void_p, POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype  = c_int
kernel32.Process32NextW.argtypes  = [c_void_p, POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype   = c_int

class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]
class MSG(Structure):
    _fields_ = [("hwnd", c_void_p),
                ("message", c_uint),
                ("wParam", c_size_t),
                ("lParam", c_longlong),
                ("time", c_uint32),
                ("pt", POINT)]
user32.PeekMessageW.argtypes = [POINTER(MSG), c_void_p, c_uint, c_uint, c_uint]
user32.PeekMessageW.restype  = c_int

WM_HOTKEY = 0x0312
VK_F1 = 0x70
VK_F9 = 0x78
VK_F10 = 0x79

# 可选的快捷键名称（F1~F12）
HOTKEY_CHOICES = [f"F{i}" for i in range(1, 13)]

def vk_from_name(name):
    """把 'F1'~'F24' 这样的名称转换成虚拟键码；非法名称返回 0"""
    s = str(name).strip().upper()
    if s.startswith("F") and s[1:].isdigit():
        n = int(s[1:])
        if 1 <= n <= 24:
            return VK_F1 + n - 1
    return 0

def name_from_vk(vk):
    """把虚拟键码转换成 'F1'~'F24' 名称；不在范围内返回空串"""
    if VK_F1 <= vk <= VK_F1 + 23:
        return f"F{vk - VK_F1 + 1}"
    return ""
TH32CS_SNAPPROCESS = 0x2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MOUSEEVENTF_LEFTDOWN  = 0x0002
MOUSEEVENTF_LEFTUP    = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP   = 0x0010

# ============================================================================
# 二点五、多语言支持（12 种语言）
# ============================================================================

LANG_CODES = ["zh_cn", "en", "de", "it", "fr", "es", "ru", "pt_br", "pl", "ja", "ko", "zh_tw"]

# 语言名称使用该语言自身写法（选择框内不翻译语言名）
LANG_NATIVE = {
    "zh_cn": "简体中文",
    "en": "English",
    "de": "Deutsch",
    "it": "Italiano",
    "fr": "Français",
    "es": "Español",
    "ru": "Русский",
    "pt_br": "Português (Brasil)",
    "pl": "Polski",
    "ja": "日本語",
    "ko": "한국어",
    "zh_tw": "繁體中文",
}

CURRENT_LANG = "zh_cn"

def _L(code, **kw):
    _TR[code] = kw

_TR = {}
_L("zh_cn",
   app_title="自动钓鱼机器人 v1.1",
   grp_status="游戏状态", grp_settings="钓鱼设置", grp_run="运行状态", grp_log="运行日志",
   lbl_proc="游戏进程:", lbl_sess="音频轨道:", lbl_vu="当前音量:",
   st_proc_off="未检测到游戏进程（请先启动游戏）", st_proc_on="已检测到游戏进程",
   st_sess_off="未找到音频轨道", st_sess_on="已连接音频轨道",
   vu_label="当前音量: [{bar}] {vu}%   （灵敏度阈值 {thr}%）",
   set_start="启动延迟(毫秒):", set_pull="收线前等待(毫秒):", set_cast="抛竿前等待(毫秒):",
   set_noise="咬钩后静默(毫秒):", set_sens="音量灵敏度(0-100):",
   set_timeout="无鱼超时(毫秒,0=禁用):", set_autostop="定时停止(分钟,0=不限):",
   set_proc="监听进程名(;分隔):",
   chk_right="使用右键点击（默认左键）", chk_top="窗口置顶", chk_hotkey="启用快捷键",
   lbl_hk_start="开始键:", lbl_hk_stop="停止键:",
   lbl_state="状态:", st_idle="空闲：按 F9 或点击“开始钓鱼”",
   stats="抛竿次数: {cast}    鱼获(收线): {fish}    运行时间: {time}",
   btn_start="开始钓鱼", btn_stop="停止", btn_running="运行中...",
   btn_no_game="未检测到游戏...", btn_stopping="正在停止...",
   btn_start_hk="开始钓鱼 ({name})", btn_stop_hk="停止 ({name})",
   hint_use="使用提示：游戏内请关闭音乐与环境音，手持鱼竿站在水边，鼠标悬停在游戏画面上。",
   hint_principle="原理：只监听游戏音频轨道音量检测咬钩，模拟鼠标点击收线/抛竿，不读写游戏内存。",
   hint_note="注意：修改声音灵敏度等设置后，点击“开始钓鱼”才会生效。",
   hint_quiet="建议在安静的环境中钓鱼，防止意外误触发。",
   dlg_about_title="关于",
   about_author="原作者为 lzzy",
   about_cn1="中文版由 PPLLAAS258 参考 C 语言使用 Python",
   about_cn2="用 DeepSeek 转换重新编写",
   btn_open_github="访问原作者 GitHub", btn_close="关闭",
   dlg_lang_title="选择语言",
   msg_no_game="未检测到游戏进程。\n默认监听进程：Terraria;tModLoader;javaw（可在设置中修改）。\n请先启动游戏，再开始钓鱼。",
   msg_sens="音量灵敏度请输入 0 到 100 之间的整数。",
   msg_no_track="未找到游戏的音频轨道。\n请确认：游戏正在运行且有声音输出（可打开系统音量合成器查看）。\n\n是否仍要继续启动？",
   msg_game_exit="检测到游戏进程已退出，机器人已自动停止。",
   msg_autostop="定时钓鱼时间已到（{n} 分钟），机器人已自动停止。",
   log_start="══════════ 新一轮钓鱼开始 ══════════",
   log_start_delay="启动延迟 {n} 毫秒，随后自动抛竿...",
   st_starting="正在启动（等待启动延迟 {n} 毫秒）...",
   log_stopped_wait="启动等待期间收到停止指令。",
   log_err_no_proc="错误：未检测到监听进程（{p}），机器人停止。",
   log_warn_no_track="警告：未找到游戏音频轨道，请确认游戏有声音输出（见系统音量合成器）。",
   log_cast1="第 1 次抛竿...",
   st_silence="静默等待 {n} 毫秒（过滤落水声）...",
   st_listening="正在监听咬钩声音...",
   log_audio_err="音频读取异常: {e}",
   log_proc_exit="检测到游戏进程已退出，机器人自动停止。",
   log_autostop="定时时间已到（{n} 分钟），机器人自动停止。",
   st_bite="检测到咬钩 (VU {v}%)！{n} 毫秒后收线...",
   log_bite="检测到咬钩 (VU {v}%)，等待 {n} 毫秒后收线...",
   log_fish="收线成功！累计鱼获 {n} 条。",
   log_recast="已重新抛竿（第 {n} 次抛竿）。",
   log_timeout="超过 {n} 毫秒无咬钩，收回鱼线并重新抛竿...",
   log_stop_cmd="收到停止指令。",
   log_end="══════════ 本轮结束：共抛竿 {c} 次，收线 {f} 次，用时 {t} 秒 ══════════",
   st_stopped="已停止",
   log_ready="Terraria 自动钓鱼机器人 v1.1（Python 多语言版）已就绪。",
   log_listen="监听进程: {p}",
   log_params="参数: 启动延迟 {start}ms / 收线延迟 {pull}ms / 抛竿延迟 {cast}ms / 静默 {noise}ms / 灵敏度 {sens} / 超时 {timeout}ms / 定时停止 {stop} 分钟",
   log_tip="提示：开始前请在游戏内关闭音乐与环境音，手持鱼竿，并保持鱼线已收回。",
   st_sessions="检测到 {n} 个音频会话: {names}",
   st_no_sessions="未枚举到任何音频会话（请确认声音设备已启用）",
   hk_invalid="快捷键名称无效，请使用 F1~F12。",
   hk_same="开始键与停止键相同，只有开始键生效。",
   hk_fail="快捷键注册失败（可能被其他程序占用），请更换按键或关闭快捷键。",
   hk_fail_stop="停止快捷键注册失败（可能被其他程序占用），请更换按键。",
   st_starting_bot="正在启动...", st_stopping_bot="正在停止...",
)
_L("en",
   app_title="Auto Fishing Bot v1.1",
   grp_status="Game Status", grp_settings="Fishing Settings", grp_run="Run Status", grp_log="Log",
   lbl_proc="Game process:", lbl_sess="Audio track:", lbl_vu="Volume:",
   st_proc_off="Game process not detected (start the game first)", st_proc_on="Game process detected",
   st_sess_off="Audio track not found", st_sess_on="Audio track connected",
   vu_label="Volume: [{bar}] {vu}%   (threshold {thr}%)",
   set_start="Start delay (ms):", set_pull="Wait before reeling (ms):", set_cast="Wait before casting (ms):",
   set_noise="Silence after bite (ms):", set_sens="Volume sensitivity (0-100):",
   set_timeout="No-bite timeout (ms, 0=off):", set_autostop="Auto stop (min, 0=unlimited):",
   set_proc="Process names (; separated):",
   chk_right="Use right click (left by default)", chk_top="Always on top", chk_hotkey="Enable hotkeys",
   lbl_hk_start="Start key:", lbl_hk_stop="Stop key:",
   lbl_state="Status:", st_idle='Idle: press F9 or click "Start Fishing"',
   stats="Casts: {cast}    Fish caught: {fish}    Runtime: {time}",
   btn_start="Start Fishing", btn_stop="Stop", btn_running="Running...",
   btn_no_game="No game detected...", btn_stopping="Stopping...",
   btn_start_hk="Start Fishing ({name})", btn_stop_hk="Stop ({name})",
   hint_use="Tip: turn off music and ambient sounds in the game, hold the rod by the water and keep the mouse over the game screen.",
   hint_principle="How it works: it listens to the volume of the game's audio track to detect bites and simulates mouse clicks to reel in/cast. It never reads or writes game memory.",
   hint_note='Note: after changing settings such as sensitivity, click "Start Fishing" to apply them.',
   hint_quiet="Fish in a quiet environment to avoid accidental triggers.",
   dlg_about_title="About",
   about_author="Original author: lzzy",
   about_cn1="Chinese version by PPLLAAS258, based on the C# original and rewritten in Python",
   about_cn2="converted and rewritten with DeepSeek",
   btn_open_github="Visit original author's GitHub", btn_close="Close",
   dlg_lang_title="Select Language",
   msg_no_game="Game process not detected.\nDefault process list: Terraria;tModLoader;javaw (editable in settings).\nPlease start the game first.",
   msg_sens="Sensitivity must be an integer between 0 and 100.",
   msg_no_track="Game audio track not found.\nMake sure the game is running and outputting sound (check the Windows volume mixer).\n\nContinue anyway?",
   msg_game_exit="The game process has exited. The bot has stopped automatically.",
   msg_autostop="Fishing time is up ({n} min). The bot has stopped automatically.",
   log_start="══════════ New fishing session started ══════════",
   log_start_delay="Start delay {n} ms, then casting automatically...",
   st_starting="Starting (waiting {n} ms start delay)...",
   log_stopped_wait="Stop requested during start delay.",
   log_err_no_proc="Error: monitored process not detected ({p}). Bot stopped.",
   log_warn_no_track="Warning: game audio track not found. Make sure the game outputs sound (see the volume mixer).",
   log_cast1="Casting (1st cast)...",
   st_silence="Waiting {n} ms of silence (filtering splash noise)...",
   st_listening="Listening for bite sounds...",
   log_audio_err="Audio read error: {e}",
   log_proc_exit="The game process has exited. The bot has stopped automatically.",
   log_autostop="Time is up ({n} min). The bot has stopped automatically.",
   st_bite="Bite detected (VU {v}%)! Reeling in after {n} ms...",
   log_bite="Bite detected (VU {v}%). Reeling in after {n} ms...",
   log_fish="Reeled in! Total fish caught: {n}.",
   log_recast="Cast again (cast #{n}).",
   log_timeout="No bite for {n} ms. Reeling in and casting again...",
   log_stop_cmd="Stop command received.",
   log_end="══════════ Session ended: {c} casts, {f} fish, {t} seconds ══════════",
   st_stopped="Stopped",
   log_ready="Terraria Auto Fishing Bot v1.1 (Python, multilingual) is ready.",
   log_listen="Monitored processes: {p}",
   log_params="Params: start delay {start}ms / pull delay {pull}ms / cast delay {cast}ms / silence {noise}ms / sensitivity {sens} / timeout {timeout}ms / auto stop {stop} min",
   log_tip="Tip: turn off music and ambient sounds, hold the rod, and make sure the line is reeled in before starting.",
   st_sessions="Detected {n} audio session(s): {names}",
   st_no_sessions="No audio sessions found (check that a sound device is enabled)",
   hk_invalid="Invalid hotkey name. Use F1~F12.",
   hk_same="Start and stop keys are the same; only the start key will work.",
   hk_fail="Hotkey registration failed (probably in use by another program). Change the key or disable hotkeys.",
   hk_fail_stop="Stop hotkey registration failed (probably in use). Change the key.",
   st_starting_bot="Starting...", st_stopping_bot="Stopping...",
)
_L("de",
   app_title="Auto-Angler-Bot v1.1",
   grp_status="Spielstatus", grp_settings="Angeleinstellungen", grp_run="Betriebsstatus", grp_log="Protokoll",
   lbl_proc="Spielprozess:", lbl_sess="Audiospur:", lbl_vu="Lautstärke:",
   st_proc_off="Spielprozess nicht gefunden (bitte zuerst das Spiel starten)", st_proc_on="Spielprozess gefunden",
   st_sess_off="Audiospur nicht gefunden", st_sess_on="Audiospur verbunden",
   vu_label="Lautstärke: [{bar}] {vu}%   (Schwelle {thr}%)",
   set_start="Startverzögerung (ms):", set_pull="Wartezeit vor dem Einholen (ms):", set_cast="Wartezeit vor dem Auswerfen (ms):",
   set_noise="Ruhe nach dem Biss (ms):", set_sens="Lautstärke-Empfindlichkeit (0-100):",
   set_timeout="Zeitlimit ohne Biss (ms, 0=aus):", set_autostop="Auto-Stopp (Min., 0=unbegrenzt):",
   set_proc="Prozessnamen (; getrennt):",
   chk_right="Rechtsklick verwenden (Standard: links)", chk_top="Immer im Vordergrund", chk_hotkey="Hotkeys aktivieren",
   lbl_hk_start="Starttaste:", lbl_hk_stop="Stopptaste:",
   lbl_state="Status:", st_idle='Bereit: F9 drücken oder "Angeln starten" klicken',
   stats="Würfe: {cast}    Fische: {fish}    Laufzeit: {time}",
   btn_start="Angeln starten", btn_stop="Stopp", btn_running="Läuft...",
   btn_no_game="Kein Spiel gefunden...", btn_stopping="Wird gestoppt...",
   btn_start_hk="Angeln starten ({name})", btn_stop_hk="Stopp ({name})",
   hint_use="Tipp: Musik und Umgebungsgeräusche im Spiel ausschalten, die Angel am Wasser halten und die Maus über dem Spielfenster lassen.",
   hint_principle="Prinzip: lauscht auf die Lautstärke der Audiospur des Spiels, um Bisse zu erkennen, und simuliert Mausklicks zum Einholen/Auswerfen; der Spielspeicher wird weder gelesen noch geschrieben.",
   hint_note='Hinweis: Änderungen (z. B. Empfindlichkeit) werden erst nach Klick auf "Angeln starten" wirksam.',
   hint_quiet="In ruhiger Umgebung angeln, um Fehlauslösungen zu vermeiden.",
   dlg_about_title="Über",
   about_author="Originalautor: lzzy",
   about_cn1="Chinesische Version von PPLLAAS258, basierend auf dem C#-Original, in Python neu geschrieben",
   about_cn2="mit DeepSeek konvertiert und neu geschrieben",
   btn_open_github="GitHub des Originalautors öffnen", btn_close="Schließen",
   dlg_lang_title="Sprache wählen",
   msg_no_game="Spielprozess nicht gefunden.\nStandard-Liste: Terraria;tModLoader;javaw (in den Einstellungen änderbar).\nBitte zuerst das Spiel starten.",
   msg_sens="Die Empfindlichkeit muss eine ganze Zahl zwischen 0 und 100 sein.",
   msg_no_track="Audiospur des Spiels nicht gefunden.\nBitte prüfen, ob das Spiel läuft und Ton ausgibt (siehe Windows-Lautstärkemixer).\n\nTrotzdem fortfahren?",
   msg_game_exit="Der Spielprozess wurde beendet. Der Bot wurde automatisch gestoppt.",
   msg_autostop="Die Angelzeit ist abgelaufen ({n} Min.). Der Bot wurde automatisch gestoppt.",
   log_start="══════════ Neue Angelsitzung gestartet ══════════",
   log_start_delay="Startverzögerung {n} ms, danach wird automatisch ausgeworfen...",
   st_starting="Startet (Startverzögerung {n} ms)...",
   log_stopped_wait="Stopp während der Startverzögerung angefordert.",
   log_err_no_proc="Fehler: überwachter Prozess nicht gefunden ({p}). Bot gestoppt.",
   log_warn_no_track="Warnung: Audiospur des Spiels nicht gefunden. Bitte prüfen, ob das Spiel Ton ausgibt (Lautstärkemixer).",
   log_cast1="Auswerfen (1. Wurf)...",
   st_silence="{n} ms Ruhe abwarten (Platschgeräusche filtern)...",
   st_listening="Auf Bissgeräusche lauschen...",
   log_audio_err="Audio-Lesefehler: {e}",
   log_proc_exit="Der Spielprozess wurde beendet. Der Bot wurde automatisch gestoppt.",
   log_autostop="Zeit abgelaufen ({n} Min.). Der Bot wurde automatisch gestoppt.",
   st_bite="Biss erkannt (VU {v}%)! Einholen in {n} ms...",
   log_bite="Biss erkannt (VU {v}%). Einholen in {n} ms...",
   log_fish="Eingeholt! Fische gesamt: {n}.",
   log_recast="Erneut ausgeworfen (Wurf Nr. {n}).",
   log_timeout="Kein Biss seit {n} ms. Einholen und erneut auswerfen...",
   log_stop_cmd="Stoppbefehl empfangen.",
   log_end="══════════ Sitzung beendet: {c} Würfe, {f} Fische, {t} Sekunden ══════════",
   st_stopped="Gestoppt",
   log_ready="Terraria Auto-Angler-Bot v1.1 (Python, mehrsprachig) ist bereit.",
   log_listen="Überwachte Prozesse: {p}",
   log_params="Parameter: Startverzögerung {start}ms / Einholen {pull}ms / Auswerfen {cast}ms / Ruhe {noise}ms / Empfindlichkeit {sens} / Zeitlimit {timeout}ms / Auto-Stopp {stop} Min.",
   log_tip="Tipp: Vor dem Start Musik und Umgebungsgeräusche ausschalten, die Angel halten und die Leine einholen.",
   st_sessions="{n} Audiositzung(en) erkannt: {names}",
   st_no_sessions="Keine Audiositzungen gefunden (bitte prüfen, ob ein Audiogerät aktiviert ist)",
   hk_invalid="Ungültiger Hotkey-Name. Bitte F1~F12 verwenden.",
   hk_same="Start- und Stopptaste sind gleich; nur die Starttaste funktioniert.",
   hk_fail="Hotkey-Registrierung fehlgeschlagen (vermutlich von anderem Programm belegt). Taste ändern oder Hotkeys deaktivieren.",
   hk_fail_stop="Registrierung der Stopptaste fehlgeschlagen (vermutlich belegt). Bitte Taste ändern.",
   st_starting_bot="Startet...", st_stopping_bot="Wird gestoppt...",
)
_L("it",
   app_title="Bot di Pesca Automatico v1.1",
   grp_status="Stato del gioco", grp_settings="Impostazioni di pesca", grp_run="Stato di esecuzione", grp_log="Registro",
   lbl_proc="Processo di gioco:", lbl_sess="Traccia audio:", lbl_vu="Volume:",
   st_proc_off="Processo di gioco non rilevato (avvia prima il gioco)", st_proc_on="Processo di gioco rilevato",
   st_sess_off="Traccia audio non trovata", st_sess_on="Traccia audio collegata",
   vu_label="Volume: [{bar}] {vu}%   (soglia {thr}%)",
   set_start="Ritardo di avvio (ms):", set_pull="Attesa prima di tirare (ms):", set_cast="Attesa prima del lancio (ms):",
   set_noise="Silenzio dopo l'abboccata (ms):", set_sens="Sensibilità del volume (0-100):",
   set_timeout="Timeout senza pesce (ms, 0=off):", set_autostop="Stop automatico (min, 0=illimitato):",
   set_proc="Nomi processo (; separati):",
   chk_right="Usa clic destro (predefinito sinistro)", chk_top="Sempre in primo piano", chk_hotkey="Abilita tasti rapidi",
   lbl_hk_start="Tasto avvio:", lbl_hk_stop="Tasto stop:",
   lbl_state="Stato:", st_idle='Inattivo: premi F9 o clicca "Avvia pesca"',
   stats="Lanci: {cast}    Pesci: {fish}    Tempo: {time}",
   btn_start="Avvia pesca", btn_stop="Stop", btn_running="In esecuzione...",
   btn_no_game="Gioco non rilevato...", btn_stopping="Arresto...",
   btn_start_hk="Avvia pesca ({name})", btn_stop_hk="Stop ({name})",
   hint_use="Suggerimento: disattiva musica e suoni ambientali nel gioco, tieni la canna vicino all'acqua e il mouse sulla finestra di gioco.",
   hint_principle="Principio: ascolta il volume della traccia audio del gioco per rilevare le abboccate e simula clic del mouse per tirare/lanciare; non legge né scrive la memoria di gioco.",
   hint_note='Nota: le modifiche (es. sensibilità) hanno effetto dopo aver cliccato "Avvia pesca".',
   hint_quiet="Pesca in un ambiente tranquillo per evitare attivazioni accidentali.",
   dlg_about_title="Informazioni",
   about_author="Autore originale: lzzy",
   about_cn1="Versione cinese di PPLLAAS258, basata sull'originale C# e riscritta in Python",
   about_cn2="convertita e riscritta con DeepSeek",
   btn_open_github="Apri il GitHub dell'autore", btn_close="Chiudi",
   dlg_lang_title="Seleziona lingua",
   msg_no_game="Processo di gioco non rilevato.\nElenco predefinito: Terraria;tModLoader;javaw (modificabile nelle impostazioni).\nAvvia prima il gioco.",
   msg_sens="La sensibilità deve essere un numero intero tra 0 e 100.",
   msg_no_track="Traccia audio del gioco non trovata.\nVerifica che il gioco sia in esecuzione e produca audio (vedi il mixer di volume di Windows).\n\nContinuare comunque?",
   msg_game_exit="Il processo di gioco è terminato. Il bot si è fermato automaticamente.",
   msg_autostop="Tempo di pesca scaduto ({n} min). Il bot si è fermato automaticamente.",
   log_start="══════════ Nuova sessione di pesca avviata ══════════",
   log_start_delay="Ritardo di avvio {n} ms, poi lancio automatico...",
   st_starting="Avvio (attesa ritardo di {n} ms)...",
   log_stopped_wait="Stop richiesto durante il ritardo di avvio.",
   log_err_no_proc="Errore: processo monitorato non rilevato ({p}). Bot fermato.",
   log_warn_no_track="Avviso: traccia audio del gioco non trovata. Verifica che il gioco produca audio (mixer di volume).",
   log_cast1="Lancio (1° lancio)...",
   st_silence="Attesa di {n} ms di silenzio (filtro rumore dello splash)...",
   st_listening="In ascolto dei suoni di abboccata...",
   log_audio_err="Errore di lettura audio: {e}",
   log_proc_exit="Il processo di gioco è terminato. Il bot si è fermato automaticamente.",
   log_autostop="Tempo scaduto ({n} min). Il bot si è fermato automaticamente.",
   st_bite="Abboccata rilevata (VU {v}%)! Tiro tra {n} ms...",
   log_bite="Abboccata rilevata (VU {v}%). Tiro tra {n} ms...",
   log_fish="Tirato su! Pesci totali: {n}.",
   log_recast="Rilanciato (lancio n. {n}).",
   log_timeout="Nessuna abboccata da {n} ms. Tiro e rilancio...",
   log_stop_cmd="Comando di stop ricevuto.",
   log_end="══════════ Sessione terminata: {c} lanci, {f} pesci, {t} secondi ══════════",
   st_stopped="Fermato",
   log_ready="Terraria Bot di Pesca Automatico v1.1 (Python, multilingue) pronto.",
   log_listen="Processi monitorati: {p}",
   log_params="Parametri: ritardo avvio {start}ms / tiro {pull}ms / lancio {cast}ms / silenzio {noise}ms / sensibilità {sens} / timeout {timeout}ms / stop automatico {stop} min",
   log_tip="Suggerimento: prima di iniziare disattiva musica e suoni ambientali, tieni la canna e la lenza riavvolta.",
   st_sessions="Rilevate {n} sessioni audio: {names}",
   st_no_sessions="Nessuna sessione audio trovata (verifica che un dispositivo audio sia abilitato)",
   hk_invalid="Nome tasto non valido. Usa F1~F12.",
   hk_same="Tasto di avvio e di stop uguali; funzionerà solo l'avvio.",
   hk_fail="Registrazione tasto fallita (probabilmente in uso da un altro programma). Cambia tasto o disattiva i tasti rapidi.",
   hk_fail_stop="Registrazione del tasto di stop fallita (probabilmente in uso). Cambia tasto.",
   st_starting_bot="Avvio...", st_stopping_bot="Arresto...",
)
_L("fr",
   app_title="Bot de pêche automatique v1.1",
   grp_status="État du jeu", grp_settings="Paramètres de pêche", grp_run="État d'exécution", grp_log="Journal",
   lbl_proc="Processus du jeu :", lbl_sess="Piste audio :", lbl_vu="Volume :",
   st_proc_off="Processus du jeu introuvable (lancez d'abord le jeu)", st_proc_on="Processus du jeu détecté",
   st_sess_off="Piste audio introuvable", st_sess_on="Piste audio connectée",
   vu_label="Volume : [{bar}] {vu}%   (seuil {thr}%)",
   set_start="Délai de démarrage (ms) :", set_pull="Attente avant de remonter (ms) :", set_cast="Attente avant de lancer (ms) :",
   set_noise="Silence après touche (ms) :", set_sens="Sensibilité du volume (0-100) :",
   set_timeout="Délai sans touche (ms, 0=désactivé) :", set_autostop="Arrêt programmé (min, 0=illimité) :",
   set_proc="Noms de processus (séparés par ;) :",
   chk_right="Utiliser le clic droit (gauche par défaut)", chk_top="Toujours au premier plan", chk_hotkey="Activer les raccourcis",
   lbl_hk_start="Touche départ :", lbl_hk_stop="Touche arrêt :",
   lbl_state="État :", st_idle='Au repos : appuyez sur F9 ou cliquez sur « Lancer la pêche »',
   stats="Lancers : {cast}    Prises : {fish}    Durée : {time}",
   btn_start="Lancer la pêche", btn_stop="Arrêter", btn_running="En cours...",
   btn_no_game="Jeu introuvable...", btn_stopping="Arrêt...",
   btn_start_hk="Lancer la pêche ({name})", btn_stop_hk="Arrêter ({name})",
   hint_use="Astuce : coupez la musique et les bruits ambiants du jeu, gardez la canne près de l'eau et la souris sur l'écran du jeu.",
   hint_principle="Principe : écoute le volume de la piste audio du jeu pour détecter les touches et simule des clics de souris pour remonter/lancer ; aucune lecture/écriture de la mémoire du jeu.",
   hint_note="Remarque : les modifications (sensibilité, etc.) ne s'appliquent qu'après avoir cliqué sur « Lancer la pêche ».",
   hint_quiet="Pêchez dans un endroit calme pour éviter les déclenchements accidentels.",
   dlg_about_title="À propos",
   about_author="Auteur original : lzzy",
   about_cn1="Version chinoise par PPLLAAS258, basée sur l'original C# et réécrite en Python",
   about_cn2="convertie et réécrite avec DeepSeek",
   btn_open_github="Voir le GitHub de l'auteur", btn_close="Fermer",
   dlg_lang_title="Choisir la langue",
   msg_no_game="Processus du jeu introuvable.\nListe par défaut : Terraria;tModLoader;javaw (modifiable dans les réglages).\nVeuillez d'abord lancer le jeu.",
   msg_sens="La sensibilité doit être un entier compris entre 0 et 100.",
   msg_no_track="Piste audio du jeu introuvable.\nVérifiez que le jeu est lancé et qu'il émet du son (voir le mélangeur de volume Windows).\n\nContinuer quand même ?",
   msg_game_exit="Le processus du jeu s'est terminé. Le bot s'est arrêté automatiquement.",
   msg_autostop="Le temps de pêche est écoulé ({n} min). Le bot s'est arrêté automatiquement.",
   log_start="══════════ Nouvelle session de pêche ══════════",
   log_start_delay="Délai de démarrage de {n} ms, puis lancer automatique...",
   st_starting="Démarrage (attente de {n} ms)...",
   log_stopped_wait="Arrêt demandé pendant le délai de démarrage.",
   log_err_no_proc="Erreur : processus surveillé introuvable ({p}). Bot arrêté.",
   log_warn_no_track="Avertissement : piste audio du jeu introuvable. Vérifiez que le jeu émet du son (mélangeur de volume).",
   log_cast1="Lancer (1er lancer)...",
   st_silence="Attente de {n} ms de silence (filtrage des éclaboussures)...",
   st_listening="À l'écoute des touches...",
   log_audio_err="Erreur de lecture audio : {e}",
   log_proc_exit="Le processus du jeu s'est terminé. Le bot s'est arrêté automatiquement.",
   log_autostop="Temps écoulé ({n} min). Le bot s'est arrêté automatiquement.",
   st_bite="Touche détectée (VU {v}%) ! Remontée dans {n} ms...",
   log_bite="Touche détectée (VU {v}%). Remontée dans {n} ms...",
   log_fish="Remonté ! Total des prises : {n}.",
   log_recast="Nouveau lancer (lancer n° {n}).",
   log_timeout="Aucune touche depuis {n} ms. Remontée et nouveau lancer...",
   log_stop_cmd="Commande d'arrêt reçue.",
   log_end="══════════ Session terminée : {c} lancers, {f} prises, {t} secondes ══════════",
   st_stopped="Arrêté",
   log_ready="Terraria Bot de pêche automatique v1.1 (Python, multilingue) prêt.",
   log_listen="Processus surveillés : {p}",
   log_params="Paramètres : démarrage {start}ms / remontée {pull}ms / lancer {cast}ms / silence {noise}ms / sensibilité {sens} / délai {timeout}ms / arrêt {stop} min",
   log_tip="Astuce : avant de commencer, coupez la musique et les sons ambiants, tenez la canne et gardez la ligne remontée.",
   st_sessions="{n} session(s) audio détectée(s) : {names}",
   st_no_sessions="Aucune session audio trouvée (vérifiez qu'un périphérique audio est activé)",
   hk_invalid="Nom de touche invalide. Utilisez F1~F12.",
   hk_same="Touches de départ et d'arrêt identiques ; seul le départ fonctionnera.",
   hk_fail="Échec de l'enregistrement du raccourci (probablement utilisé par un autre programme). Changez de touche ou désactivez les raccourcis.",
   hk_fail_stop="Échec de l'enregistrement de la touche d'arrêt (probablement utilisée). Changez de touche.",
   st_starting_bot="Démarrage...", st_stopping_bot="Arrêt...",
)
_L("es",
   app_title="Bot de pesca automático v1.1",
   grp_status="Estado del juego", grp_settings="Ajustes de pesca", grp_run="Estado de ejecución", grp_log="Registro",
   lbl_proc="Proceso del juego:", lbl_sess="Pista de audio:", lbl_vu="Volumen:",
   st_proc_off="Proceso del juego no detectado (inicia el juego primero)", st_proc_on="Proceso del juego detectado",
   st_sess_off="Pista de audio no encontrada", st_sess_on="Pista de audio conectada",
   vu_label="Volumen: [{bar}] {vu}%   (umbral {thr}%)",
   set_start="Retardo de inicio (ms):", set_pull="Espera antes de recoger (ms):", set_cast="Espera antes de lanzar (ms):",
   set_noise="Silencio tras picada (ms):", set_sens="Sensibilidad de volumen (0-100):",
   set_timeout="Tiempo sin picada (ms, 0=desactivado):", set_autostop="Parada programada (min, 0=ilimitado):",
   set_proc="Nombres de proceso (separados por ;):",
   chk_right="Usar clic derecho (izquierdo por defecto)", chk_top="Siempre visible", chk_hotkey="Activar atajos",
   lbl_hk_start="Tecla inicio:", lbl_hk_stop="Tecla parada:",
   lbl_state="Estado:", st_idle='Inactivo: pulsa F9 o haz clic en "Iniciar pesca"',
   stats="Lanzamientos: {cast}    Peces: {fish}    Tiempo: {time}",
   btn_start="Iniciar pesca", btn_stop="Detener", btn_running="Ejecutando...",
   btn_no_game="Juego no detectado...", btn_stopping="Deteniendo...",
   btn_start_hk="Iniciar pesca ({name})", btn_stop_hk="Detener ({name})",
   hint_use="Consejo: desactiva la música y los sonidos ambientales del juego, sujeta la caña junto al agua y mantén el ratón sobre la pantalla del juego.",
   hint_principle="Principio: escucha el volumen de la pista de audio del juego para detectar picadas y simula clics del ratón para recoger/lanzar; no lee ni escribe la memoria del juego.",
   hint_note='Nota: los cambios (sensibilidad, etc.) se aplican al hacer clic en "Iniciar pesca".',
   hint_quiet="Pesca en un entorno tranquilo para evitar disparos accidentales.",
   dlg_about_title="Acerca de",
   about_author="Autor original: lzzy",
   about_cn1="Versión china de PPLLAAS258, basada en el original C# y reescrita en Python",
   about_cn2="convertida y reescrita con DeepSeek",
   btn_open_github="Abrir GitHub del autor", btn_close="Cerrar",
   dlg_lang_title="Seleccionar idioma",
   msg_no_game="Proceso del juego no detectado.\nLista por defecto: Terraria;tModLoader;javaw (editable en los ajustes).\nInicia el juego primero.",
   msg_sens="La sensibilidad debe ser un número entero entre 0 y 100.",
   msg_no_track="Pista de audio del juego no encontrada.\nComprueba que el juego esté en marcha y emita sonido (mira el mezclador de volumen de Windows).\n\n¿Continuar de todos modos?",
   msg_game_exit="El proceso del juego ha terminado. El bot se ha detenido automáticamente.",
   msg_autostop="El tiempo de pesca ha terminado ({n} min). El bot se ha detenido automáticamente.",
   log_start="══════════ Nueva sesión de pesca iniciada ══════════",
   log_start_delay="Retardo de inicio {n} ms y lanzamiento automático...",
   st_starting="Iniciando (espera de {n} ms)...",
   log_stopped_wait="Parada solicitada durante el retardo de inicio.",
   log_err_no_proc="Error: proceso vigilado no detectado ({p}). Bot detenido.",
   log_warn_no_track="Aviso: pista de audio del juego no encontrada. Comprueba que el juego emite sonido (mezclador de volumen).",
   log_cast1="Lanzando (1er lanzamiento)...",
   st_silence="Esperando {n} ms de silencio (filtrado de salpicaduras)...",
   st_listening="Escuchando sonidos de picada...",
   log_audio_err="Error de lectura de audio: {e}",
   log_proc_exit="El proceso del juego ha terminado. El bot se ha detenido automáticamente.",
   log_autostop="Tiempo agotado ({n} min). El bot se ha detenido automáticamente.",
   st_bite="¡Picada detectada (VU {v}%)! Recogiendo en {n} ms...",
   log_bite="Picada detectada (VU {v}%). Recogiendo en {n} ms...",
   log_fish="¡Recogido! Peces en total: {n}.",
   log_recast="Lanzado de nuevo (lanzamiento n.º {n}).",
   log_timeout="Sin picadas durante {n} ms. Recogiendo y lanzando de nuevo...",
   log_stop_cmd="Comando de parada recibido.",
   log_end="══════════ Sesión terminada: {c} lanzamientos, {f} peces, {t} segundos ══════════",
   st_stopped="Detenido",
   log_ready="Terraria Bot de pesca automático v1.1 (Python, multilingüe) listo.",
   log_listen="Procesos vigilados: {p}",
   log_params="Parámetros: inicio {start}ms / recogida {pull}ms / lanzamiento {cast}ms / silencio {noise}ms / sensibilidad {sens} / tiempo límite {timeout}ms / parada {stop} min",
   log_tip="Consejo: antes de empezar, apaga la música y los sonidos ambientales, sujeta la caña y mantén el sedal recogido.",
   st_sessions="{n} sesión(es) de audio detectada(s): {names}",
   st_no_sessions="No se encontraron sesiones de audio (comprueba que haya un dispositivo de audio habilitado)",
   hk_invalid="Nombre de tecla no válido. Usa F1~F12.",
   hk_same="Las teclas de inicio y parada son iguales; solo funcionará la de inicio.",
   hk_fail="Error al registrar el atajo (probablemente en uso por otro programa). Cambia la tecla o desactiva los atajos.",
   hk_fail_stop="Error al registrar la tecla de parada (probablemente en uso). Cambia la tecla.",
   st_starting_bot="Iniciando...", st_stopping_bot="Deteniendo...",
)
_L("ru",
   app_title="Автоматический рыболовный бот v1.1",
   grp_status="Состояние игры", grp_settings="Настройки рыбалки", grp_run="Состояние работы", grp_log="Журнал",
   lbl_proc="Процесс игры:", lbl_sess="Аудиоканал:", lbl_vu="Громкость:",
   st_proc_off="Процесс игры не найден (сначала запустите игру)", st_proc_on="Процесс игры обнаружен",
   st_sess_off="Аудиоканал не найден", st_sess_on="Аудиоканал подключён",
   vu_label="Громкость: [{bar}] {vu}%   (порог {thr}%)",
   set_start="Задержка запуска (мс):", set_pull="Пауза перед подсечкой (мс):", set_cast="Пауза перед забросом (мс):",
   set_noise="Тишина после поклёвки (мс):", set_sens="Чувствительность громкости (0-100):",
   set_timeout="Таймаут без поклёвки (мс, 0=выкл):", set_autostop="Автоостановка (мин, 0=без лимита):",
   set_proc="Имена процессов (через ;):",
   chk_right="Правая кнопка мыши (по умолчанию левая)", chk_top="Поверх окон", chk_hotkey="Включить горячие клавиши",
   lbl_hk_start="Клавиша старта:", lbl_hk_stop="Клавиша стопа:",
   lbl_state="Состояние:", st_idle='Ожидание: нажмите F9 или кнопку «Начать рыбалку»',
   stats="Забросов: {cast}    Рыб: {fish}    Время: {time}",
   btn_start="Начать рыбалку", btn_stop="Стоп", btn_running="Работает...",
   btn_no_game="Игра не найдена...", btn_stopping="Остановка...",
   btn_start_hk="Начать рыбалку ({name})", btn_stop_hk="Стоп ({name})",
   hint_use="Совет: выключите музыку и фоновые звуки в игре, держите удочку у воды, а курсор — над окном игры.",
   hint_principle="Принцип: слушает громкость аудиоканала игры, чтобы определить поклёвку, и имитирует клики мыши для подсечки/заброса; память игры не читается и не изменяется.",
   hint_note='Примечание: изменения (чувствительность и др.) вступают в силу после нажатия «Начать рыбалку».',
   hint_quiet="Рыбачьте в тихом месте, чтобы избежать ложных срабатываний.",
   dlg_about_title="О программе",
   about_author="Автор оригинала: lzzy",
   about_cn1="Китайская версия — PPLLAAS258, на основе оригинала C#, переписана на Python",
   about_cn2="конвертирована и переписана с помощью DeepSeek",
   btn_open_github="Открыть GitHub автора", btn_close="Закрыть",
   dlg_lang_title="Выбор языка",
   msg_no_game="Процесс игры не найден.\nСписок по умолчанию: Terraria;tModLoader;javaw (можно изменить в настройках).\nСначала запустите игру.",
   msg_sens="Чувствительность должна быть целым числом от 0 до 100.",
   msg_no_track="Аудиоканал игры не найден.\nУбедитесь, что игра запущена и выводит звук (см. микшер громкости Windows).\n\nВсё равно продолжить?",
   msg_game_exit="Процесс игры завершён. Бот автоматически остановлен.",
   msg_autostop="Время рыбалки истекло ({n} мин). Бот автоматически остановлен.",
   log_start="══════════ Начата новая рыболовная сессия ══════════",
   log_start_delay="Задержка запуска {n} мс, затем автоматический заброс...",
   st_starting="Запуск (ожидание {n} мс)...",
   log_stopped_wait="Получена команда остановки во время задержки запуска.",
   log_err_no_proc="Ошибка: наблюдаемый процесс не найден ({p}). Бот остановлен.",
   log_warn_no_track="Предупреждение: аудиоканал игры не найден. Убедитесь, что игра выводит звук (микшер громкости).",
   log_cast1="Заброс (1-й заброс)...",
   st_silence="Ожидание {n} мс тишины (фильтр всплесков)...",
   st_listening="Прослушивание звуков поклёвки...",
   log_audio_err="Ошибка чтения аудио: {e}",
   log_proc_exit="Процесс игры завершён. Бот автоматически остановлен.",
   log_autostop="Время истекло ({n} мин). Бот автоматически остановлен.",
   st_bite="Поклёвка (VU {v}%)! Подсечка через {n} мс...",
   log_bite="Поклёвка (VU {v}%). Подсечка через {n} мс...",
   log_fish="Подсечено! Всего рыб: {n}.",
   log_recast="Новый заброс (заброс №{n}).",
   log_timeout="Поклёвок нет уже {n} мс. Подсечка и новый заброс...",
   log_stop_cmd="Получена команда остановки.",
   log_end="══════════ Сессия завершена: забросов {c}, рыб {f}, время {t} с ══════════",
   st_stopped="Остановлено",
   log_ready="Terraria: автоматический рыболовный бот v1.1 (Python, мультиязычный) готов.",
   log_listen="Наблюдаемые процессы: {p}",
   log_params="Параметры: запуск {start}мс / подсечка {pull}мс / заброс {cast}мс / тишина {noise}мс / чувствительность {sens} / таймаут {timeout}мс / автостоп {stop} мин",
   log_tip="Совет: перед началом выключите музыку и фоновые звуки, держите удочку и смотанную леску.",
   st_sessions="Обнаружено аудиосессий: {n}: {names}",
   st_no_sessions="Аудиосессии не найдены (проверьте, что звуковое устройство включено)",
   hk_invalid="Неверное имя клавиши. Используйте F1~F12.",
   hk_same="Клавиши старта и стопа совпадают; будет работать только старт.",
   hk_fail="Не удалось зарегистрировать горячую клавишу (вероятно, занята другой программой). Смените клавишу или отключите горячие клавиши.",
   hk_fail_stop="Не удалось зарегистрировать клавишу стопа (вероятно, занята). Смените клавишу.",
   st_starting_bot="Запуск...", st_stopping_bot="Остановка...",
)
_L("pt_br",
   app_title="Bot de Pesca Automático v1.1",
   grp_status="Status do jogo", grp_settings="Configurações de pesca", grp_run="Status de execução", grp_log="Registro",
   lbl_proc="Processo do jogo:", lbl_sess="Trilha de áudio:", lbl_vu="Volume:",
   st_proc_off="Processo do jogo não detectado (inicie o jogo primeiro)", st_proc_on="Processo do jogo detectado",
   st_sess_off="Trilha de áudio não encontrada", st_sess_on="Trilha de áudio conectada",
   vu_label="Volume: [{bar}] {vu}%   (limiar {thr}%)",
   set_start="Atraso de início (ms):", set_pull="Espera antes de puxar (ms):", set_cast="Espera antes de lançar (ms):",
   set_noise="Silêncio após a fisgada (ms):", set_sens="Sensibilidade do volume (0-100):",
   set_timeout="Tempo sem fisgada (ms, 0=desativado):", set_autostop="Parada automática (min, 0=ilimitado):",
   set_proc="Nomes de processo (; separados):",
   chk_right="Usar clique direito (esquerdo por padrão)", chk_top="Sempre no topo", chk_hotkey="Ativar atalhos",
   lbl_hk_start="Tecla iniciar:", lbl_hk_stop="Tecla parar:",
   lbl_state="Status:", st_idle='Ocioso: pressione F9 ou clique em "Iniciar pesca"',
   stats="Lançamentos: {cast}    Peixes: {fish}    Tempo: {time}",
   btn_start="Iniciar pesca", btn_stop="Parar", btn_running="Executando...",
   btn_no_game="Jogo não detectado...", btn_stopping="Parando...",
   btn_start_hk="Iniciar pesca ({name})", btn_stop_hk="Parar ({name})",
   hint_use="Dica: desligue a música e os sons ambientes do jogo, segure a vara perto da água e mantenha o mouse sobre a janela do jogo.",
   hint_principle="Princípio: escuta o volume da trilha de áudio do jogo para detectar fisgadas e simula cliques do mouse para puxar/lançar; não lê nem grava a memória do jogo.",
   hint_note='Nota: as alterações (sensibilidade etc.) só valem após clicar em "Iniciar pesca".',
   hint_quiet="Pesque em um ambiente silencioso para evitar disparos acidentais.",
   dlg_about_title="Sobre",
   about_author="Autor original: lzzy",
   about_cn1="Versão chinesa de PPLLAAS258, baseada no original C# e reescrita em Python",
   about_cn2="convertida e reescrita com DeepSeek",
   btn_open_github="Abrir GitHub do autor", btn_close="Fechar",
   dlg_lang_title="Selecionar idioma",
   msg_no_game="Processo do jogo não detectado.\nLista padrão: Terraria;tModLoader;javaw (editável nas configurações).\nInicie o jogo primeiro.",
   msg_sens="A sensibilidade deve ser um número inteiro entre 0 e 100.",
   msg_no_track="Trilha de áudio do jogo não encontrada.\nVerifique se o jogo está rodando e emitindo som (veja o mixer de volume do Windows).\n\nContinuar mesmo assim?",
   msg_game_exit="O processo do jogo foi encerrado. O bot parou automaticamente.",
   msg_autostop="O tempo de pesca terminou ({n} min). O bot parou automaticamente.",
   log_start="══════════ Nova sessão de pesca iniciada ══════════",
   log_start_delay="Atraso de início de {n} ms e lançamento automático...",
   st_starting="Iniciando (aguardando {n} ms)...",
   log_stopped_wait="Parada solicitada durante o atraso de início.",
   log_err_no_proc="Erro: processo monitorado não detectado ({p}). Bot parado.",
   log_warn_no_track="Aviso: trilha de áudio do jogo não encontrada. Verifique se o jogo emite som (mixer de volume).",
   log_cast1="Lançando (1º lançamento)...",
   st_silence="Aguardando {n} ms de silêncio (filtrando ruído do respingo)...",
   st_listening="Ouvindo sons de fisgada...",
   log_audio_err="Erro de leitura de áudio: {e}",
   log_proc_exit="O processo do jogo foi encerrado. O bot parou automaticamente.",
   log_autostop="Tempo esgotado ({n} min). O bot parou automaticamente.",
   st_bite="Fisgada detectada (VU {v}%)! Puxando em {n} ms...",
   log_bite="Fisgada detectada (VU {v}%). Puxando em {n} ms...",
   log_fish="Puxado! Total de peixes: {n}.",
   log_recast="Lançado novamente (lançamento nº {n}).",
   log_timeout="Sem fisgadas por {n} ms. Puxando e lançando novamente...",
   log_stop_cmd="Comando de parada recebido.",
   log_end="══════════ Sessão encerrada: {c} lançamentos, {f} peixes, {t} segundos ══════════",
   st_stopped="Parado",
   log_ready="Terraria Bot de Pesca Automático v1.1 (Python, multilíngue) pronto.",
   log_listen="Processos monitorados: {p}",
   log_params="Parâmetros: início {start}ms / puxar {pull}ms / lançar {cast}ms / silêncio {noise}ms / sensibilidade {sens} / tempo limite {timeout}ms / parada {stop} min",
   log_tip="Dica: antes de começar, desligue música e sons ambientes, segure a vara e mantenha a linha recolhida.",
   st_sessions="{n} sessão(ões) de áudio detectada(s): {names}",
   st_no_sessions="Nenhuma sessão de áudio encontrada (verifique se um dispositivo de áudio está habilitado)",
   hk_invalid="Nome de tecla inválido. Use F1~F12.",
   hk_same="As teclas de iniciar e parar são iguais; apenas a de iniciar funcionará.",
   hk_fail="Falha ao registrar o atalho (provavelmente em uso por outro programa). Troque a tecla ou desative os atalhos.",
   hk_fail_stop="Falha ao registrar a tecla de parar (provavelmente em uso). Troque a tecla.",
   st_starting_bot="Iniciando...", st_stopping_bot="Parando...",
)
_L("pl",
   app_title="Automatyczny Bot Wędkarski v1.1",
   grp_status="Status gry", grp_settings="Ustawienia wędkowania", grp_run="Status działania", grp_log="Dziennik",
   lbl_proc="Proces gry:", lbl_sess="Ścieżka audio:", lbl_vu="Głośność:",
   st_proc_off="Nie wykryto procesu gry (najpierw uruchom grę)", st_proc_on="Wykryto proces gry",
   st_sess_off="Nie znaleziono ścieżki audio", st_sess_on="Połączono ścieżkę audio",
   vu_label="Głośność: [{bar}] {vu}%   (próg {thr}%)",
   set_start="Opóźnienie startu (ms):", set_pull="Czekanie przed zwinięciem (ms):", set_cast="Czekanie przed zarzuceniem (ms):",
   set_noise="Cisza po braniu (ms):", set_sens="Czułość głośności (0-100):",
   set_timeout="Limit bez brań (ms, 0=wył.):", set_autostop="Auto-stop (min, 0=bez limitu):",
   set_proc="Nazwy procesów (rozdzielone ;):",
   chk_right="Użyj prawego klawisza (domyślnie lewy)", chk_top="Zawsze na wierzchu", chk_hotkey="Włącz skróty",
   lbl_hk_start="Klawisz startu:", lbl_hk_stop="Klawisz stopu:",
   lbl_state="Status:", st_idle='Bezczynny: naciśnij F9 lub kliknij "Rozpocznij wędkowanie"',
   stats="Rzuty: {cast}    Ryby: {fish}    Czas: {time}",
   btn_start="Rozpocznij wędkowanie", btn_stop="Stop", btn_running="Działa...",
   btn_no_game="Nie wykryto gry...", btn_stopping="Zatrzymywanie...",
   btn_start_hk="Rozpocznij wędkowanie ({name})", btn_stop_hk="Stop ({name})",
   hint_use="Wskazówka: wyłącz muzykę i dźwięki otoczenia w grze, trzymaj wędkę przy wodzie, a kursor nad oknem gry.",
   hint_principle="Zasada: nasłuchuje głośności ścieżki audio gry, aby wykryć branie, i symuluje kliknięcia myszy do zwijania/zarzucania; nie odczytuje ani nie zapisuje pamięci gry.",
   hint_note='Uwaga: zmiany (np. czułości) obowiązują po kliknięciu "Rozpocznij wędkowanie".',
   hint_quiet="Łów w cichym otoczeniu, aby uniknąć przypadkowych aktywacji.",
   dlg_about_title="O programie",
   about_author="Oryginalny autor: lzzy",
   about_cn1="Wersja chińska: PPLLAAS258, na podstawie oryginału C#, przepisana w Pythonie",
   about_cn2="skonwertowana i przepisana z pomocą DeepSeek",
   btn_open_github="Otwórz GitHub autora", btn_close="Zamknij",
   dlg_lang_title="Wybierz język",
   msg_no_game="Nie wykryto procesu gry.\nLista domyślna: Terraria;tModLoader;javaw (można zmienić w ustawieniach).\nNajpierw uruchom grę.",
   msg_sens="Czułość musi być liczbą całkowitą od 0 do 100.",
   msg_no_track="Nie znaleziono ścieżki audio gry.\nUpewnij się, że gra działa i odtwarza dźwięk (sprawdź mikser głośności systemu Windows).\n\nKontynuować mimo to?",
   msg_game_exit="Proces gry został zamknięty. Bot zatrzymał się automatycznie.",
   msg_autostop="Czas wędkowania minął ({n} min). Bot zatrzymał się automatycznie.",
   log_start="══════════ Rozpoczęto nową sesję wędkowania ══════════",
   log_start_delay="Opóźnienie startu {n} ms, potem automatyczne zarzucenie...",
   st_starting="Uruchamianie (oczekiwanie {n} ms)...",
   log_stopped_wait="Zażądano zatrzymania podczas opóźnienia startu.",
   log_err_no_proc="Błąd: nie wykryto monitorowanego procesu ({p}). Bot zatrzymany.",
   log_warn_no_track="Ostrzeżenie: nie znaleziono ścieżki audio gry. Upewnij się, że gra odtwarza dźwięk (mikser głośności).",
   log_cast1="Zarzucanie (1. rzut)...",
   st_silence="Oczekiwanie {n} ms ciszy (filtrowanie plusku)...",
   st_listening="Nasłuchiwanie odgłosów brań...",
   log_audio_err="Błąd odczytu audio: {e}",
   log_proc_exit="Proces gry został zamknięty. Bot zatrzymał się automatycznie.",
   log_autostop="Czas minął ({n} min). Bot zatrzymał się automatycznie.",
   st_bite="Wykryto branie (VU {v}%)! Zwinięcie za {n} ms...",
   log_bite="Wykryto branie (VU {v}%). Zwinięcie za {n} ms...",
   log_fish="Zwinięto! Ryb łącznie: {n}.",
   log_recast="Zarzucono ponownie (rzut nr {n}).",
   log_timeout="Brak brań od {n} ms. Zwinięcie i ponowne zarzucenie...",
   log_stop_cmd="Otrzymano polecenie zatrzymania.",
   log_end="══════════ Sesja zakończona: rzutów {c}, ryb {f}, czas {t} s ══════════",
   st_stopped="Zatrzymano",
   log_ready="Terraria Automatyczny Bot Wędkarski v1.1 (Python, wielojęzyczny) gotowy.",
   log_listen="Monitorowane procesy: {p}",
   log_params="Parametry: start {start}ms / zwijanie {pull}ms / zarzucanie {cast}ms / cisza {noise}ms / czułość {sens} / limit {timeout}ms / auto-stop {stop} min",
   log_tip="Wskazówka: przed startem wyłącz muzykę i dźwięki otoczenia, trzymaj wędkę i zwiniętą żyłkę.",
   st_sessions="Wykryto sesje audio: {n}: {names}",
   st_no_sessions="Nie znaleziono sesji audio (sprawdź, czy urządzenie audio jest włączone)",
   hk_invalid="Nieprawidłowa nazwa klawisza. Użyj F1~F12.",
   hk_same="Klawisze startu i stopu są takie same; zadziała tylko start.",
   hk_fail="Nie udało się zarejestrować skrótu (prawdopodobnie zajęty przez inny program). Zmień klawisz lub wyłącz skróty.",
   hk_fail_stop="Nie udało się zarejestrować klawisza stopu (prawdopodobnie zajęty). Zmień klawisz.",
   st_starting_bot="Uruchamianie...", st_stopping_bot="Zatrzymywanie...",
)
_L("ja",
   app_title="自動釣りボット v1.1",
   grp_status="ゲーム状態", grp_settings="釣り設定", grp_run="実行状態", grp_log="ログ",
   lbl_proc="ゲームプロセス:", lbl_sess="オーディオトラック:", lbl_vu="音量:",
   st_proc_off="ゲームプロセス未検出（先にゲームを起動してください）", st_proc_on="ゲームプロセスを検出",
   st_sess_off="オーディオトラックが見つかりません", st_sess_on="オーディオトラック接続済み",
   vu_label="音量: [{bar}] {vu}%   （しきい値 {thr}%）",
   set_start="開始遅延(ms):", set_pull="巻き取り前待機(ms):", set_cast="キャスト前待機(ms):",
   set_noise="バイト後静音(ms):", set_sens="音量感度(0-100):",
   set_timeout="無反応タイムアウト(ms, 0=無効):", set_autostop="自動停止(分, 0=無制限):",
   set_proc="監視プロセス名(;区切り):",
   chk_right="右クリックを使用（デフォルトは左）", chk_top="常に最前面", chk_hotkey="ホットキーを有効化",
   lbl_hk_start="開始キー:", lbl_hk_stop="停止キー:",
   lbl_state="状態:", st_idle='待機中: F9または「釣り開始」をクリック',
   stats="キャスト: {cast}    釣果: {fish}    時間: {time}",
   btn_start="釣り開始", btn_stop="停止", btn_running="実行中...",
   btn_no_game="ゲーム未検出...", btn_stopping="停止中...",
   btn_start_hk="釣り開始 ({name})", btn_stop_hk="停止 ({name})",
   hint_use="ヒント: ゲーム内の音楽と環境音をオフにし、水辺で釣竿を持ち、マウスをゲーム画面の上に置いてください。",
   hint_principle="原理: ゲームのオーディオトラックの音量を監視してバイトを検出し、マウスクリックをシミュレートします。ゲームメモリの読み書きは行いません。",
   hint_note='注意: 感度などの設定変更は「釣り開始」をクリックした後に反映されます。',
   hint_quiet="誤作動を防ぐため、静かな環境で釣りをしてください。",
   dlg_about_title="このアプリについて",
   about_author="原作者: lzzy",
   about_cn1="中国語版は PPLLAAS258 が C# オリジナルを参考に Python で書き直し",
   about_cn2="DeepSeek で変換・書き直し",
   btn_open_github="原作者のGitHubを開く", btn_close="閉じる",
   dlg_lang_title="言語を選択",
   msg_no_game="ゲームプロセスが見つかりません。\nデフォルト監視リスト: Terraria;tModLoader;javaw（設定で変更可）。\n先にゲームを起動してください。",
   msg_sens="感度は0〜100の整数で入力してください。",
   msg_no_track="ゲームのオーディオトラックが見つかりません。\nゲームが起動していて音声を出力しているか確認してください（Windowsの音量ミキサーを参照）。\n\nそれでも続行しますか？",
   msg_game_exit="ゲームプロセスが終了したため、ボットを自動停止しました。",
   msg_autostop="釣り時間が終了しました（{n}分）。ボットを自動停止しました。",
   log_start="══════════ 新しい釣りセッション開始 ══════════",
   log_start_delay="開始遅延 {n}ms、その後自動キャスト...",
   st_starting="起動中（開始遅延 {n}ms 待機）...",
   log_stopped_wait="開始遅延中に停止指示を受け取りました。",
   log_err_no_proc="エラー: 監視プロセス未検出（{p}）。ボットを停止しました。",
   log_warn_no_track="警告: ゲームのオーディオトラックが見つかりません。ゲームが音声を出力しているか確認してください（音量ミキサー）。",
   log_cast1="キャスト（1回目）...",
   st_silence="{n}ms 静音待機（着水音をフィルタ）...",
   st_listening="バイト音を監視中...",
   log_audio_err="オーディオ読み取りエラー: {e}",
   log_proc_exit="ゲームプロセスが終了したため、ボットを自動停止しました。",
   log_autostop="時間になりました（{n}分）。ボットを自動停止しました。",
   st_bite="バイト検出 (VU {v}%)！{n}ms 後に巻き取り...",
   log_bite="バイト検出 (VU {v}%)、{n}ms 後に巻き取り...",
   log_fish="巻き取り成功！累計釣果 {n} 匹。",
   log_recast="再キャスト（{n} 回目）。",
   log_timeout="{n}ms バイトなし。巻き取って再キャスト...",
   log_stop_cmd="停止指示を受信しました。",
   log_end="══════════ セッション終了: キャスト {c} 回、釣果 {f} 匹、時間 {t} 秒 ══════════",
   st_stopped="停止済み",
   log_ready="Terraria 自動釣りボット v1.1（Python多言語版）の準備ができました。",
   log_listen="監視プロセス: {p}",
   log_params="パラメータ: 開始遅延 {start}ms / 巻き取り {pull}ms / キャスト {cast}ms / 静音 {noise}ms / 感度 {sens} / タイムアウト {timeout}ms / 自動停止 {stop}分",
   log_tip="ヒント: 開始前にゲーム内の音楽と環境音をオフにし、釣竿を持ち、釣り糸を巻き取っておいてください。",
   st_sessions="オーディオセッション {n} 件を検出: {names}",
   st_no_sessions="オーディオセッションが見つかりません（サウンドデバイスが有効か確認してください）",
   hk_invalid="キー名が無効です。F1〜F12を使用してください。",
   hk_same="開始キーと停止キーが同じです。開始キーのみ有効になります。",
   hk_fail="ホットキーの登録に失敗しました（他のプログラムが使用中の可能性）。キーを変更するかホットキーを無効にしてください。",
   hk_fail_stop="停止キーの登録に失敗しました（使用中の可能性）。キーを変更してください。",
   st_starting_bot="起動中...", st_stopping_bot="停止中...",
)
_L("ko",
   app_title="자동 낚시 봇 v1.1",
   grp_status="게임 상태", grp_settings="낚시 설정", grp_run="실행 상태", grp_log="로그",
   lbl_proc="게임 프로세스:", lbl_sess="오디오 트랙:", lbl_vu="음량:",
   st_proc_off="게임 프로세스를 찾을 수 없음(게임을 먼저 실행하세요)", st_proc_on="게임 프로세스 감지됨",
   st_sess_off="오디오 트랙을 찾을 수 없음", st_sess_on="오디오 트랙 연결됨",
   vu_label="음량: [{bar}] {vu}%   (임계값 {thr}%)",
   set_start="시작 지연(ms):", set_pull="낚아채기 전 대기(ms):", set_cast="던지기 전 대기(ms):",
   set_noise="입질 후 침묵(ms):", set_sens="음량 감도(0-100):",
   set_timeout="입질 없음 시간초과(ms, 0=끔):", set_autostop="자동 중지(분, 0=무제한):",
   set_proc="프로세스 이름(; 구분):",
   chk_right="오른쪽 클릭 사용(기본 왼쪽)", chk_top="항상 위", chk_hotkey="단축키 사용",
   lbl_hk_start="시작 키:", lbl_hk_stop="중지 키:",
   lbl_state="상태:", st_idle='대기 중: F9 또는 "낚시 시작" 클릭',
   stats="던짐: {cast}    잡은 물고기: {fish}    시간: {time}",
   btn_start="낚시 시작", btn_stop="중지", btn_running="실행 중...",
   btn_no_game="게임 감지 안 됨...", btn_stopping="중지 중...",
   btn_start_hk="낚시 시작 ({name})", btn_stop_hk="중지 ({name})",
   hint_use="팁: 게임에서 음악과 환경음을 끄고, 물가에서 낚싯대를 든 채 마우스를 게임 화면 위에 두세요.",
   hint_principle="원리: 게임 오디오 트랙의 음량을 들어 입질을 감지하고 마우스 클릭을 흉내냅니다. 게임 메모리를 읽거나 쓰지 않습니다.",
   hint_note='참고: 감도 등의 설정 변경은 "낚시 시작"을 클릭해야 적용됩니다.',
   hint_quiet="오작동을 막으려면 조용한 환경에서 낚시하세요.",
   dlg_about_title="정보",
   about_author="원작자: lzzy",
   about_cn1="중국어 버전은 PPLLAAS258이 C# 원본을 참고해 Python으로 다시 작성",
   about_cn2="DeepSeek로 변환 및 재작성",
   btn_open_github="원작자 GitHub 열기", btn_close="닫기",
   dlg_lang_title="언어 선택",
   msg_no_game="게임 프로세스를 찾을 수 없습니다.\n기본 목록: Terraria;tModLoader;javaw(설정에서 변경 가능).\n먼저 게임을 실행하세요.",
   msg_sens="감도는 0~100 사이의 정수여야 합니다.",
   msg_no_track="게임 오디오 트랙을 찾을 수 없습니다.\n게임이 실행 중이고 소리가 출력되는지 확인하세요(Windows 볼륨 믹서 참조).\n\n그래도 계속하시겠습니까?",
   msg_game_exit="게임 프로세스가 종료되어 봇이 자동으로 중지되었습니다.",
   msg_autostop="낚시 시간이 끝났습니다({n}분). 봇이 자동으로 중지되었습니다.",
   log_start="══════════ 새 낚시 세션 시작 ══════════",
   log_start_delay="시작 지연 {n}ms 후 자동으로 던집니다...",
   st_starting="시작 중(시작 지연 {n}ms 대기)...",
   log_stopped_wait="시작 지연 중 중지 요청을 받았습니다.",
   log_err_no_proc="오류: 감시 프로세스를 찾을 수 없음({p}). 봇을 중지했습니다.",
   log_warn_no_track="경고: 게임 오디오 트랙을 찾을 수 없습니다. 게임이 소리를 출력하는지 확인하세요(볼륨 믹서).",
   log_cast1="던지기(1회차)...",
   st_silence="{n}ms 침묵 대기(첨벙 소리 필터링)...",
   st_listening="입질 소리 듣는 중...",
   log_audio_err="오디오 읽기 오류: {e}",
   log_proc_exit="게임 프로세스가 종료되어 봇이 자동으로 중지되었습니다.",
   log_autostop="시간이 되었습니다({n}분). 봇이 자동으로 중지되었습니다.",
   st_bite="입질 감지(VU {v}%)! {n}ms 후 낚아챔...",
   log_bite="입질 감지(VU {v}%), {n}ms 후 낚아챔...",
   log_fish="낚아챔! 누적 {n}마리.",
   log_recast="다시 던짐({n}회차).",
   log_timeout="{n}ms 동안 입질 없음. 낚아채고 다시 던짐...",
   log_stop_cmd="중지 명령을 받았습니다.",
   log_end="══════════ 세션 종료: 던짐 {c}회, 물고기 {f}마리, 시간 {t}초 ══════════",
   st_stopped="중지됨",
   log_ready="Terraria 자동 낚시 봇 v1.1(Python 다국어) 준비 완료.",
   log_listen="감시 프로세스: {p}",
   log_params="파라미터: 시작 지연 {start}ms / 낚아채기 {pull}ms / 던지기 {cast}ms / 침묵 {noise}ms / 감도 {sens} / 시간초과 {timeout}ms / 자동 중지 {stop}분",
   log_tip="팁: 시작 전에 게임 음악과 환경음을 끄고, 낚싯대를 들고, 낚싯줄을 감아 두세요.",
   st_sessions="오디오 세션 {n}개 감지: {names}",
   st_no_sessions="오디오 세션을 찾을 수 없음(사운드 장치가 활성화되어 있는지 확인하세요)",
   hk_invalid="잘못된 키 이름입니다. F1~F12를 사용하세요.",
   hk_same="시작 키와 중지 키가 같습니다. 시작 키만 작동합니다.",
   hk_fail="단축키 등록 실패(다른 프로그램이 사용 중일 수 있음). 키를 바꾸거나 단축키를 끄세요.",
   hk_fail_stop="중지 키 등록 실패(사용 중일 수 있음). 키를 바꾸세요.",
   st_starting_bot="시작 중...", st_stopping_bot="중지 중...",
)
_L("zh_tw",
   app_title="自動釣魚機器人 v1.1",
   grp_status="遊戲狀態", grp_settings="釣魚設定", grp_run="執行狀態", grp_log="執行日誌",
   lbl_proc="遊戲進程:", lbl_sess="音訊軌道:", lbl_vu="目前音量:",
   st_proc_off="未偵測到遊戲進程（請先啟動遊戲）", st_proc_on="已偵測到遊戲進程",
   st_sess_off="未找到音訊軌道", st_sess_on="已連接音訊軌道",
   vu_label="目前音量: [{bar}] {vu}%   （靈敏度閾值 {thr}%）",
   set_start="啟動延遲(毫秒):", set_pull="收線前等待(毫秒):", set_cast="拋竿前等待(毫秒):",
   set_noise="咬鉤後靜默(毫秒):", set_sens="音量靈敏度(0-100):",
   set_timeout="無魚超時(毫秒,0=停用):", set_autostop="定時停止(分鐘,0=不限):",
   set_proc="監聽進程名(;分隔):",
   chk_right="使用右鍵點擊（預設左鍵）", chk_top="視窗置頂", chk_hotkey="啟用快捷鍵",
   lbl_hk_start="開始鍵:", lbl_hk_stop="停止鍵:",
   lbl_state="狀態:", st_idle="閒置：按 F9 或點擊「開始釣魚」",
   stats="拋竿次數: {cast}    魚獲(收線): {fish}    執行時間: {time}",
   btn_start="開始釣魚", btn_stop="停止", btn_running="執行中...",
   btn_no_game="未偵測到遊戲...", btn_stopping="正在停止...",
   btn_start_hk="開始釣魚 ({name})", btn_stop_hk="停止 ({name})",
   hint_use="使用提示：遊戲內請關閉音樂與環境音，手持魚竿站在水邊，滑鼠懸停在遊戲畫面上。",
   hint_principle="原理：只監聽遊戲音訊軌道音量偵測咬鉤，模擬滑鼠點擊收線/拋竿，不讀寫遊戲記憶體。",
   hint_note="注意：修改聲音靈敏度等設定後，點擊「開始釣魚」才會生效。",
   hint_quiet="建議在安靜的環境中釣魚，防止意外誤觸發。",
   dlg_about_title="關於",
   about_author="原作者為 lzzy",
   about_cn1="中文版由 PPLLAAS258 參考 C 語言使用 Python",
   about_cn2="用 DeepSeek 轉換重新編寫",
   btn_open_github="造訪原作者 GitHub", btn_close="關閉",
   dlg_lang_title="選擇語言",
   msg_no_game="未偵測到遊戲進程。\n預設監聽進程：Terraria;tModLoader;javaw（可在設定中修改）。\n請先啟動遊戲，再開始釣魚。",
   msg_sens="音量靈敏度請輸入 0 到 100 之間的整數。",
   msg_no_track="未找到遊戲的音訊軌道。\n請確認：遊戲正在執行且有聲音輸出（可開啟系統音量合成器查看）。\n\n是否仍要繼續啟動？",
   msg_game_exit="偵測到遊戲進程已退出，機器人已自動停止。",
   msg_autostop="定時釣魚時間已到（{n} 分鐘），機器人已自動停止。",
   log_start="══════════ 新一輪釣魚開始 ══════════",
   log_start_delay="啟動延遲 {n} 毫秒，隨後自動拋竿...",
   st_starting="正在啟動（等待啟動延遲 {n} 毫秒）...",
   log_stopped_wait="啟動等待期間收到停止指令。",
   log_err_no_proc="錯誤：未偵測到監聽進程（{p}），機器人停止。",
   log_warn_no_track="警告：未找到遊戲音訊軌道，請確認遊戲有聲音輸出（見系統音量合成器）。",
   log_cast1="第 1 次拋竿...",
   st_silence="靜默等待 {n} 毫秒（過濾落水聲）...",
   st_listening="正在監聽咬鉤聲音...",
   log_audio_err="音訊讀取異常: {e}",
   log_proc_exit="偵測到遊戲進程已退出，機器人已自動停止。",
   log_autostop="定時時間已到（{n} 分鐘），機器人自動停止。",
   st_bite="偵測到咬鉤 (VU {v}%)！{n} 毫秒後收線...",
   log_bite="偵測到咬鉤 (VU {v}%)，等待 {n} 毫秒後收線...",
   log_fish="收線成功！累計魚獲 {n} 條。",
   log_recast="已重新拋竿（第 {n} 次拋竿）。",
   log_timeout="超過 {n} 毫秒無咬鉤，收回魚線並重新拋竿...",
   log_stop_cmd="收到停止指令。",
   log_end="══════════ 本輪結束：共拋竿 {c} 次，收線 {f} 次，用時 {t} 秒 ══════════",
   st_stopped="已停止",
   log_ready="Terraria 自動釣魚機器人 v1.1（Python 多語言版）已就緒。",
   log_listen="監聽進程: {p}",
   log_params="參數: 啟動延遲 {start}ms / 收線延遲 {pull}ms / 拋竿延遲 {cast}ms / 靜默 {noise}ms / 靈敏度 {sens} / 超時 {timeout}ms / 定時停止 {stop} 分鐘",
   log_tip="提示：開始前請在遊戲內關閉音樂與環境音，手持魚竿，並保持魚線已收回。",
   st_sessions="偵測到 {n} 個音訊工作階段: {names}",
   st_no_sessions="未列舉到任何音訊工作階段（請確認聲音裝置已啟用）",
   hk_invalid="快捷鍵名稱無效，請使用 F1~F12。",
   hk_same="開始鍵與停止鍵相同，只有開始鍵生效。",
   hk_fail="快捷鍵註冊失敗（可能被其他程式占用），請更換按鍵或關閉快捷鍵。",
   hk_fail_stop="停止快捷鍵註冊失敗（可能被其他程式占用），請更換按鍵。",
   st_starting_bot="正在啟動...", st_stopping_bot="正在停止...",
)

TRANS = _TR

def T(key, **kw):
    """取当前语言的翻译文本；kw 为格式化参数"""
    d = TRANS.get(CURRENT_LANG, TRANS["zh_cn"])
    s = d.get(key, TRANS["zh_cn"].get(key, key))
    if kw:
        try:
            s = s.format(**kw)
        except Exception:
            pass
    return s

def normalize_lang(code):
    """语言代码归一化：任何无效、缺失或未知的语言配置一律回退到简体中文（zh_cn）"""
    if code in TRANS:
        return code
    return "zh_cn"

def set_lang(code):
    """切换全局语言；无效代码自动回退到简体中文"""
    global CURRENT_LANG
    CURRENT_LANG = normalize_lang(code)

def app_title():
    """窗口/弹窗标题：Terraria 为固定英文品牌名，其余部分随语言翻译"""
    return f"Terraria {T('app_title')}"

# ============================================================================
# 三、工具函数：进程匹配 / 音量读取
# ============================================================================

def match_proc_name(exe_name, proc_list):
    """判断进程名（可带 .exe）是否在监听列表里"""
    base = os.path.splitext(exe_name)[0].lower()
    for tok in proc_list.replace(',', ';').replace('|', ';').split(';'):
        t = os.path.splitext(tok.strip())[0].lower()
        if t and t == base:
            return True
    return False

def process_exists_any(proc_list):
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == -1:
        return False
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    found = False
    try:
        if kernel32.Process32FirstW(snap, byref(pe)):
            while True:
                if match_proc_name(pe.szExeFile, proc_list):
                    found = True
                    break
                if not kernel32.Process32NextW(snap, byref(pe)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return found

def pid_to_name_toolhelp(pid):
    """后备方案：从进程快照按 PID 找名字（不需要 OpenProcess 权限）"""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == -1:
        return ""
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    name = ""
    try:
        if kernel32.Process32FirstW(snap, byref(pe)):
            while True:
                if pe.th32ProcessID == pid:
                    name = pe.szExeFile
                    break
                if not kernel32.Process32NextW(snap, byref(pe)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return name

def proc_name_by_pid(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    name = ""
    if h:
        buf = (c_wchar * 260)()
        if psapi.GetModuleBaseNameW(h, None, buf, 260) > 0:
            name = buf.value
        kernel32.CloseHandle(h)
    if not name:
        name = pid_to_name_toolhelp(pid)   # OpenProcess 失败时用快照兜底
    return name

def qi(p, iid):
    """COM QueryInterface 辅助：p 为接口指针"""
    out = c_void_p()
    hr = cast(p, POINTER(IUnknown)).contents.lpVtbl.contents.QueryInterface(
        cast(p, POINTER(IUnknown)), byref(iid), byref(out))
    return hr, out

def com_release(p):
    cast(p, POINTER(IUnknown)).contents.lpVtbl.contents.Release(
        cast(p, POINTER(IUnknown)))

# 最近一次枚举到的全部音频会话 [(pid, 进程名), ...]，用于诊断显示
AUDIO_SESSIONS = []
DEVICE_STATE_ACTIVE = 0x1

def _read_meter_vu(sess_p):
    """对会话 QI 出 IAudioMeterInformation 并读取峰值音量，返回 0.0~1.0；失败返回 0.0"""
    hr, meter = qi(sess_p, IID_IAudioMeterInformation)
    if hr < 0 or not meter.value:
        return 0.0
    vu = 0.0
    meter_p = cast(meter, POINTER(IAudioMeterInformation))
    try:
        ch = c_uint(0)
        if meter_p.contents.lpVtbl.contents.GetMeteringChannelCount(meter_p, byref(ch)) >= 0 and ch.value > 0:
            vals = (c_float * ch.value)()
            if meter_p.contents.lpVtbl.contents.GetChannelsPeakValues(meter_p, ch.value, vals) >= 0:
                for c in range(ch.value):
                    if vals[c] > vu:
                        vu = vals[c]
    finally:
        com_release(meter_p)
    return vu

def _scan_sessions_on_device(dev_p, proc_list):
    """枚举某个音频设备上的全部会话，返回 (匹配会话的最大峰值音量, 是否找到匹配会话)"""
    vu = 0.0
    found = False
    mgr = c_void_p()
    if dev_p.contents.lpVtbl.contents.Activate(dev_p, byref(IID_IAudioSessionManager2),
                                               CLSCTX_ALL, None, byref(mgr)) < 0 or not mgr.value:
        return vu, found
    mgr_p = cast(mgr, POINTER(IAudioSessionManager2))
    en = c_void_p()
    hr = mgr_p.contents.lpVtbl.contents.GetSessionEnumerator(mgr_p, byref(en))
    com_release(mgr_p)
    if hr < 0 or not en.value:
        return vu, found
    en_p = cast(en, POINTER(IAudioSessionEnumerator))
    count = c_int(0)
    if en_p.contents.lpVtbl.contents.GetCount(en_p, byref(count)) >= 0:
        for i in range(count.value):
            try:
                ctl = c_void_p()
                if en_p.contents.lpVtbl.contents.GetSession(en_p, i, byref(ctl)) < 0 or not ctl.value:
                    continue
                # 关键修复：GetSession 返回的是 IAudioSessionControl*，原版 C# 会先
                # QI 成 IAudioSessionControl2 再调 GetProcessId。直接按 Control2 的
                # vtable 调用可能取到错误的函数槽，导致拿不到进程名 → 会话匹配失败。
                ctl2 = c_void_p()
                hr2 = cast(ctl, POINTER(IUnknown)).contents.lpVtbl.contents.QueryInterface(
                    cast(ctl, POINTER(IUnknown)), byref(IID_IAudioSessionControl2), byref(ctl2))
                if hr2 >= 0 and ctl2.value:
                    sess_p = cast(ctl2, POINTER(IAudioSessionControl2))
                else:
                    sess_p = cast(ctl, POINTER(IAudioSessionControl2))
                pid = c_uint32(0)
                name = ""
                if sess_p.contents.lpVtbl.contents.GetProcessId(sess_p, byref(pid)) >= 0 and pid.value:
                    name = proc_name_by_pid(pid.value)
                if name:
                    AUDIO_SESSIONS.append((pid.value, name))
                if name and match_proc_name(name, proc_list):
                    v = _read_meter_vu(sess_p)
                    if v > vu:
                        vu = v
                    found = True
                if hr2 >= 0 and ctl2.value:
                    com_release(sess_p)                                   # 释放 QI 出的引用
                com_release(cast(ctl, POINTER(IAudioSessionControl2)))    # 释放 GetSession 的引用
            except Exception:
                continue
    com_release(en_p)
    return vu, found

def get_game_vu(proc_list):
    """核心函数：读取目标进程音频轨道的峰值音量。
       返回 (进程是否找到, 音频轨道是否找到, 峰值音量 0.0~1.0)
       比原版更健壮：默认多媒体设备 → 默认控制台设备 → 全部活动渲染设备依次扫描"""
    global AUDIO_SESSIONS
    proc_found = process_exists_any(proc_list)
    sess_found = False
    vu = 0.0
    AUDIO_SESSIONS = []

    denum = c_void_p()
    hr = ole32.CoCreateInstance(byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                                byref(IID_IMMDeviceEnumerator), byref(denum))
    if hr < 0 or not denum.value:
        return proc_found, sess_found, vu
    denum_p = cast(denum, POINTER(IMMDeviceEnumerator))

    devices = []
    # 1) 默认多媒体设备（原版使用的角色）
    dev = c_void_p()
    if denum_p.contents.lpVtbl.contents.GetDefaultAudioEndpoint(denum_p, 0, 1, byref(dev)) >= 0 and dev.value:
        devices.append(dev)
    # 2) 默认控制台设备（部分声卡/远程桌面没有多媒体角色，退回使用）
    dev2 = c_void_p()
    if denum_p.contents.lpVtbl.contents.GetDefaultAudioEndpoint(denum_p, 0, 0, byref(dev2)) >= 0 and dev2.value:
        devices.append(dev2)
    # 3) 枚举全部活动状态的渲染设备（游戏可能输出到非默认设备）
    coll = c_void_p()
    if denum_p.contents.lpVtbl.contents.EnumAudioEndpoints(denum_p, 0, DEVICE_STATE_ACTIVE, byref(coll)) >= 0 and coll.value:
        coll_p = cast(coll, POINTER(IMMDeviceCollection))
        try:
            n = c_uint(0)
            if coll_p.contents.lpVtbl.contents.GetCount(coll_p, byref(n)) >= 0:
                for k in range(n.value):
                    d = c_void_p()
                    if coll_p.contents.lpVtbl.contents.Item(coll_p, k, byref(d)) >= 0 and d.value:
                        devices.append(d)
        finally:
            com_release(coll_p)

    seen = set()
    for d in devices:
        if not d.value or d.value in seen:
            continue
        seen.add(d.value)
        dev_p = cast(d, POINTER(IMMDevice))
        try:
            v, f = _scan_sessions_on_device(dev_p, proc_list)
        except Exception:
            v, f = 0.0, False
        if v > vu:
            vu = v
        if f:
            sess_found = True
        com_release(dev_p)
        if sess_found:
            break
    com_release(denum_p)
    return proc_found, sess_found, vu

# ============================================================================
# 四、配置存取（TerrariaAutoFishPy.ini）
# ============================================================================

def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

INI_PATH = os.path.join(app_dir(), "TerrariaAutoFishPy.ini")

DEFAULTS = {
    "startdelay": 10000,   # 启动延迟(毫秒)
    "pulldelay": 0,        # 收线前等待(毫秒)
    "castdelay": 500,      # 抛竿前等待(毫秒)
    "noisedelay": 1000,    # 咬钩后静默(毫秒)
    "vusens": 5,           # 音量灵敏度(0-100)
    "timeoutms": 120000,   # 无鱼超时(毫秒, 0=禁用)
    "autostopmin": 0,      # 定时停止(分钟, 0=不限)
    "useright": 0,         # 1=使用右键点击（默认左键）
    "hotkeys": 1,          # 1=启用快捷键
    "hotkeystart": "F9",   # 开始钓鱼快捷键
    "hotkeystop": "F10",   # 停止快捷键
    "lang": "zh_cn",       # 界面语言
    "procnames": "Terraria;tModLoader;javaw",
}

def load_config():
    cp = configparser.ConfigParser()
    cfg = dict(DEFAULTS)
    try:
        if os.path.exists(INI_PATH):
            cp.read(INI_PATH, encoding="utf-8")
            for k in cfg:
                if k in ("procnames", "hotkeystart", "hotkeystop", "lang"):
                    v = cp.get("Settings", k, fallback=DEFAULTS[k])
                    cfg[k] = v.strip() or DEFAULTS[k]
                else:
                    cfg[k] = cp.getint("Settings", k, fallback=DEFAULTS[k])
    except Exception:
        cfg = dict(DEFAULTS)
    # 找不到语言配置项、值为空或为无效代码时，一律回退到简体中文
    cfg["lang"] = normalize_lang(cfg.get("lang", "zh_cn"))
    return cfg

def save_config(cfg):
    cp = configparser.ConfigParser()
    cp["Settings"] = {k: str(v) for k, v in cfg.items()}
    try:
        with open(INI_PATH, "w", encoding="utf-8") as f:
            cp.write(f)
    except Exception:
        pass

# ============================================================================
# 五、共享状态 / 消息队列
# ============================================================================

ui_q = queue.Queue()          # 工作线程 -> 主线程 的 UI 消息
evt_stop = threading.Event()  # 停止请求
evt_quit = threading.Event()  # 程序退出

shared = {
    "running": False,
    "proc_found": False,
    "sess_found": False,
    "vu_pct": 0,
    "fish": 0,
    "cast": 0,
    "start_t": 0.0,
    "elapsed": 0,
    "procnames": DEFAULTS["procnames"],
    "hotkey_enabled": True,
    "hotkey_start_vk": VK_F9,
    "hotkey_stop_vk": VK_F10,
}
shared_lock = threading.Lock()

def put_log(text):
    ui_q.put(("log", text))

def put_status(text):
    ui_q.put(("status", text))

def put_alert(kind, title, text):
    ui_q.put(("alert", kind, title, text))

def now_str():
    return time.strftime("%H:%M:%S")

# ============================================================================
# 六、状态监视线程（界面实时显示进程/轨道/音量）
# ============================================================================

_last_sess_sig = [""]
_last_audio_err = [""]

def monitor_thread():
    ole32.CoInitializeEx(None, 0)
    try:
        while not evt_quit.is_set():
            with shared_lock:
                proc_list = shared.get("procnames", DEFAULTS["procnames"])
            try:
                pf, sf, vu = get_game_vu(proc_list)
                pct = min(100, int(vu * 100.0 + 0.5))
                with shared_lock:
                    shared["proc_found"] = pf
                    shared["sess_found"] = sf
                    shared["vu_pct"] = pct
                # 音频会话列表变化时输出一次，方便排查"找不到音频轨道"的问题
                sig = "|".join(f"{pid}:{name}" for pid, name in AUDIO_SESSIONS)
                if sig != _last_sess_sig[0]:
                    _last_sess_sig[0] = sig
                    if AUDIO_SESSIONS:
                        names = ", ".join(name for _, name in AUDIO_SESSIONS[:12])
                        put_log(T("st_sessions", n=len(AUDIO_SESSIONS), names=names))
                    else:
                        put_log(T("st_no_sessions"))
            except Exception as e:
                if str(e) != _last_audio_err[0]:
                    _last_audio_err[0] = str(e)
                    put_log(T("log_audio_err", e=e))
            time.sleep(0.2)
    finally:
        ole32.CoUninitialize()

# ============================================================================
# 七、全局热键线程（F9 开始 / F10 停止）
# ============================================================================

def hotkey_thread():
    """热键线程：按当前配置注册/注销 F1~F12 热键，配置变化时自动重新注册"""
    msg = MSG()
    cur = (False, 0, 0)      # (是否启用, 开始键VK, 停止键VK)
    last_warn = [""]
    while not evt_quit.is_set():
        with shared_lock:
            enabled = bool(shared.get("hotkey_enabled", True))
            start_vk = int(shared.get("hotkey_start_vk", VK_F9))
            stop_vk = int(shared.get("hotkey_stop_vk", VK_F10))
        want = (enabled, start_vk, stop_vk)
        if want != cur:
            # 先注销旧热键
            if cur[0]:
                user32.UnregisterHotKey(None, 1)
                user32.UnregisterHotKey(None, 2)
            cur = want
            # 再按新配置注册
            if enabled:
                warn = ""
                ok = True
                if not start_vk or not stop_vk:
                    ok = False
                    warn = T("hk_invalid")
                elif start_vk == stop_vk:
                    warn = T("hk_same")
                if ok and start_vk and not user32.RegisterHotKey(None, 1, 0, start_vk):
                    ok = False
                    warn = T("hk_fail")
                if ok and stop_vk and stop_vk != start_vk and not user32.RegisterHotKey(None, 2, 0, stop_vk):
                    warn = T("hk_fail_stop")
                if warn and warn != last_warn[0]:
                    last_warn[0] = warn
                    put_log(warn)
        # 处理热键消息
        while user32.PeekMessageW(byref(msg), None, 0, 0, 1):
            if msg.message == WM_HOTKEY:
                if msg.wParam == 1:
                    ui_q.put(("hotkey_start",))
                elif msg.wParam == 2:
                    ui_q.put(("hotkey_stop",))
        time.sleep(0.05)
    if cur[0]:
        user32.UnregisterHotKey(None, 1)
        user32.UnregisterHotKey(None, 2)

# ============================================================================
# 八、钓鱼机器人线程（核心循环）
# ============================================================================

def do_click(use_right=0):
    """模拟一次鼠标点击（收线/抛竿）；use_right=1 时使用右键"""
    down = MOUSEEVENTF_RIGHTDOWN if use_right else MOUSEEVENTF_LEFTDOWN
    up   = MOUSEEVENTF_RIGHTUP   if use_right else MOUSEEVENTF_LEFTUP
    user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.1)
    user32.mouse_event(up, 0, 0, 0, 0)

def bot_thread(cfg):
    ole32.CoInitializeEx(None, 0)
    start_t = time.monotonic()
    try:
        proc_list = cfg["procnames"]
        put_log(T("log_start"))
        put_log(T("log_start_delay", n=cfg["startdelay"]))
        put_status(T("st_starting", n=cfg["startdelay"]))
        if evt_stop.wait(cfg["startdelay"] / 1000.0):
            put_log(T("log_stopped_wait"))
            return

        # 启动前再确认一次游戏进程与音频轨道
        pf, sf, _ = get_game_vu(proc_list)
        if not pf:
            put_log(T("log_err_no_proc", p=proc_list))
            put_alert("warn", app_title(), T("msg_no_game"))
            return
        if not sf:
            put_log(T("log_warn_no_track"))

        put_log(T("log_cast1"))
        do_click(cfg["useright"])
        with shared_lock:
            shared["cast"] = 1
            shared["start_t"] = start_t

        # 主循环：静默等待 → 监听咬钩 → 收线 → 抛竿 → 重复
        while not evt_stop.is_set():
            put_status(T("st_silence", n=cfg["noisedelay"]))
            if evt_stop.wait(cfg["noisedelay"] / 1000.0):
                break

            put_status(T("st_listening"))
            t0 = time.monotonic()
            bite = False
            vu_bite = 0
            while not evt_stop.is_set():
                try:
                    pf, sf, vu = get_game_vu(proc_list)
                except Exception as e:
                    put_log(T("log_audio_err", e=e))
                    pf, sf, vu = True, False, 0.0
                pct = min(100, int(vu * 100.0 + 0.5))
                with shared_lock:
                    shared["proc_found"] = pf
                    shared["sess_found"] = sf
                    shared["vu_pct"] = pct
                if not pf:
                    put_log(T("log_proc_exit"))
                    put_alert("info", app_title(), T("msg_game_exit"))
                    return
                if pct >= cfg["vusens"]:
                    bite = True
                    vu_bite = pct
                    break
                if cfg["timeoutms"] > 0 and (time.monotonic() - t0) * 1000.0 >= cfg["timeoutms"]:
                    break
                time.sleep(0.12)
            if evt_stop.is_set():
                break

            # 定时停止检查
            if cfg["autostopmin"] > 0 and (time.monotonic() - start_t) / 60.0 >= cfg["autostopmin"]:
                put_log(T("log_autostop", n=cfg["autostopmin"]))
                put_alert("info", app_title(), T("msg_autostop", n=cfg["autostopmin"]))
                break

            if bite:
                put_status(T("st_bite", v=vu_bite, n=cfg["pulldelay"]))
                put_log(T("log_bite", v=vu_bite, n=cfg["pulldelay"]))
                if evt_stop.wait(cfg["pulldelay"] / 1000.0):
                    break
                do_click(cfg["useright"])      # 收线
                with shared_lock:
                    shared["fish"] += 1
                    n = shared["fish"]
                put_log(T("log_fish", n=n))
                if evt_stop.wait(cfg["castdelay"] / 1000.0):
                    break
                do_click(cfg["useright"])      # 重新抛竿
                with shared_lock:
                    shared["cast"] += 1
                    m = shared["cast"]
                put_log(T("log_recast", n=m))
            else:
                put_log(T("log_timeout", n=cfg["timeoutms"]))
                do_click(cfg["useright"])
                if evt_stop.wait(cfg["castdelay"] / 1000.0):
                    break
                do_click(cfg["useright"])
                with shared_lock:
                    shared["cast"] += 1

        if evt_stop.is_set():
            put_log(T("log_stop_cmd"))
        with shared_lock:
            shared["elapsed"] = int(time.monotonic() - start_t)
            fish_n = shared["fish"]
            cast_n = shared["cast"]
            el = shared["elapsed"]
        put_log(T("log_end", c=cast_n, f=fish_n, t=el))
        put_status(T("st_stopped"))
    finally:
        with shared_lock:
            shared["running"] = False
        ole32.CoUninitialize()

# ============================================================================
# 九、界面（tkinter，多语言）
# ============================================================================

class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        # 第一次启动或找不到语言配置（缺失/为空/无效）时：默认使用简体中文
        set_lang(normalize_lang(self.cfg.get("lang", "zh_cn")))
        self.cfg["lang"] = CURRENT_LANG   # 把无效配置修正为实际生效的语言，后续保存时自动修复 ini
        self.threads = []

        # 状态变量（必须在 _build_ui 之前创建）
        self.var_right = tk.IntVar(value=int(self.cfg["useright"]))
        self.var_top = tk.IntVar(value=0)
        self.var_hotkey = tk.IntVar(value=int(self.cfg["hotkeys"]))

        with shared_lock:
            shared["procnames"] = self.cfg["procnames"]
            shared["hotkey_enabled"] = bool(self.cfg["hotkeys"])
            shared["hotkey_start_vk"] = vk_from_name(self.cfg["hotkeystart"]) or VK_F9
            shared["hotkey_stop_vk"] = vk_from_name(self.cfg["hotkeystop"]) or VK_F10

        root.title(app_title())
        root.resizable(True, True)   # 支持最大化窗口
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.font = ("Microsoft YaHei", 10)
        self.font_small = ("Microsoft YaHei", 9)

        self._build_ui()

        # 初始界面状态
        self.put_log(T("log_ready"))
        self.put_log(T("log_listen", p=self.cfg["procnames"]))
        self.put_log(T("log_params", start=self.cfg["startdelay"], pull=self.cfg["pulldelay"],
                       cast=self.cfg["castdelay"], noise=self.cfg["noisedelay"],
                       sens=self.cfg["vusens"], timeout=self.cfg["timeoutms"],
                       stop=self.cfg["autostopmin"]))
        self.put_log(T("log_tip"))
        self.status_var.set(T("st_idle"))
        # 启动时也按保存的语言自适应窗口大小
        self._fit_window()

        # 后台线程
        t1 = threading.Thread(target=monitor_thread, daemon=True)
        t2 = threading.Thread(target=hotkey_thread, daemon=True)
        t1.start(); t2.start()
        self.threads = [t1, t2]

        self._last = {"proc": -1, "sess": -1, "vu": -1, "fish": -1, "cast": -1,
                      "elapsed": -1, "ui": -1, "hk": None, "status": ""}
        self.poll()

    # ---------- 界面构建 ----------
    def _build_ui(self):
        pad = {"padx": 4, "pady": 2}

        # 组框 1：游戏状态
        f1 = tk.LabelFrame(self.root, text=f" {T('grp_status')} ", font=self.font)
        f1.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(f1, text=T("lbl_proc"), font=self.font).grid(row=0, column=0, sticky="w", **pad)
        self.lbl_proc = tk.Label(f1, text=T("st_proc_off"), fg="#C80000", font=self.font)
        self.lbl_proc.grid(row=0, column=1, sticky="w", **pad)
        tk.Label(f1, text=T("lbl_sess"), font=self.font).grid(row=1, column=0, sticky="w", **pad)
        self.lbl_sess = tk.Label(f1, text=T("st_sess_off"), fg="#C80000", font=self.font)
        self.lbl_sess.grid(row=1, column=1, sticky="w", **pad)
        tk.Label(f1, text=T("lbl_vu"), font=self.font).grid(row=2, column=0, sticky="w", **pad)
        self.lbl_vu = tk.Label(f1, text=T("vu_label", bar="░░░░░░░░░░░░", vu=0, thr=self.cfg.get("vusens", 5)),
                               font=self.font)
        self.lbl_vu.grid(row=2, column=1, sticky="w", **pad)

        # 组框 2：钓鱼设置
        f2 = tk.LabelFrame(self.root, text=f" {T('grp_settings')} ", font=self.font)
        f2.pack(fill="x", padx=8, pady=4)
        # 数值设置项：用 Spinbox 提供上下箭头，点箭头即可加减数值（也可直接输入）
        # 每项格式：(翻译键, 配置键, 默认值, (最小值, 最大值, 步进值))
        rows = [
            ("set_start", "startdelay", 10000, (1, 60000, 1000)),
            ("set_pull", "pulldelay", 0, (0, 60000, 100)),
            ("set_cast", "castdelay", 500, (0, 60000, 100)),
            ("set_noise", "noisedelay", 1000, (0, 60000, 100)),
            ("set_sens", "vusens", 5, (0, 100, 2)),
            ("set_timeout", "timeoutms", 120000, (0, 600000, 1000)),
            ("set_autostop", "autostopmin", 0, (0, 9999, 1)),
        ]
        self.entries = {}
        for i, (tkey, key, default, rng) in enumerate(rows):
            r, c = divmod(i, 2)
            lo, hi, inc = rng
            tk.Label(f2, text=T(tkey), font=self.font_small).grid(row=r, column=c * 2, sticky="w", **pad)
            e = ttk.Spinbox(f2, from_=lo, to=hi, increment=inc, width=10, font=self.font)
            e.insert(0, str(self.cfg.get(key, default)))
            e.grid(row=r, column=c * 2 + 1, sticky="w", **pad)
            self.entries[key] = e
        tk.Label(f2, text=T("set_proc"), font=self.font_small).grid(row=4, column=0, sticky="w", **pad)
        e = tk.Entry(f2, width=30, font=self.font)
        e.insert(0, self.cfg["procnames"])
        e.grid(row=4, column=1, columnspan=3, sticky="w", **pad)
        self.entries["procnames"] = e
        self.chk_right = tk.Checkbutton(f2, text=T("chk_right"), variable=self.var_right, font=self.font_small)
        self.chk_right.grid(row=5, column=0, columnspan=2, sticky="w", **pad)
        self.setting_widgets = list(self.entries.values()) + [self.chk_right]

        # 组框 3：运行状态
        f3 = tk.LabelFrame(self.root, text=f" {T('grp_run')} ", font=self.font)
        f3.pack(fill="x", padx=8, pady=4)
        tk.Label(f3, text=T("lbl_state"), font=self.font).grid(row=0, column=0, sticky="w", **pad)
        self.status_var = tk.StringVar(value=T("st_idle"))
        tk.Label(f3, textvariable=self.status_var, font=self.font).grid(row=0, column=1, sticky="w", **pad)
        self.stats_var = tk.StringVar(value=T("stats", cast=0, fish=0, time="00:00:00"))
        tk.Label(f3, textvariable=self.stats_var, font=self.font).grid(row=1, column=0, columnspan=2, sticky="w", **pad)

        # 按钮行
        fb = tk.Frame(self.root)
        fb.pack(fill="x", padx=8, pady=4)
        self.btn_start = tk.Button(fb, text=T("btn_start"), font=("Microsoft YaHei", 11, "bold"),
                                   width=13, height=2, command=self.start_bot)
        self.btn_start.pack(side="left", padx=(0, 4))
        self.btn_stop = tk.Button(fb, text=T("btn_stop"), font=("Microsoft YaHei", 11, "bold"),
                                  width=8, height=2, state="disabled", command=self.stop_bot)
        self.btn_stop.pack(side="left", padx=4)
        self.chk_top = tk.Checkbutton(fb, text=T("chk_top"), variable=self.var_top,
                                      font=self.font, command=self.toggle_topmost)
        self.chk_top.pack(side="left", padx=4)
        # GitHub 与 Language 按钮：按用户要求不翻译，保持英文
        self.btn_github = tk.Button(fb, text="GitHub", font=("Microsoft YaHei", 11, "bold"),
                                    width=8, height=2, command=self.show_about)
        self.btn_github.pack(side="left", padx=4)
        self.btn_lang = tk.Button(fb, text="Language", font=("Microsoft YaHei", 11, "bold"),
                                  width=8, height=2, command=self.show_language_dialog)
        self.btn_lang.pack(side="left", padx=4)

        # 快捷键设置（位于窗口置顶下方附近）
        fh = tk.Frame(self.root)
        fh.pack(fill="x", padx=8, pady=(0, 4))
        tk.Checkbutton(fh, text=T("chk_hotkey"), variable=self.var_hotkey,
                       font=self.font_small).pack(side="left", padx=4)
        tk.Label(fh, text=T("lbl_hk_start"), font=self.font_small).pack(side="left")
        self.cmb_hotkey_start = ttk.Combobox(fh, values=HOTKEY_CHOICES, width=5, font=self.font_small)
        self.cmb_hotkey_start.set(str(self.cfg.get("hotkeystart", "F9")))
        self.cmb_hotkey_start.pack(side="left", padx=(0, 10))
        tk.Label(fh, text=T("lbl_hk_stop"), font=self.font_small).pack(side="left")
        self.cmb_hotkey_stop = ttk.Combobox(fh, values=HOTKEY_CHOICES, width=5, font=self.font_small)
        self.cmb_hotkey_stop.set(str(self.cfg.get("hotkeystop", "F10")))
        self.cmb_hotkey_stop.pack(side="left")

        # 组框 4：运行日志
        f4 = tk.LabelFrame(self.root, text=f" {T('grp_log')} ", font=self.font)
        f4.pack(fill="both", expand=True, padx=8, pady=4)
        self.txt_log = scrolledtext.ScrolledText(f4, height=10, font=("Consolas", 9),
                                                 state="disabled", wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=4, pady=4)

        # 底部提示（保存引用：语言切换后按窗口宽度自动换行）
        h1 = tk.Label(self.root, text=T("hint_use"), font=self.font_small, fg="#555555")
        h1.pack(anchor="w", padx=8)
        h2 = tk.Label(self.root, text=T("hint_principle"), font=self.font_small, fg="#555555")
        h2.pack(anchor="w", padx=8)
        h3 = tk.Label(self.root, text=T("hint_note"), font=self.font_small, fg="#C80000")
        h3.pack(anchor="w", padx=8)
        h4 = tk.Label(self.root, text=T("hint_quiet"), font=self.font_small, fg="#C80000")
        h4.pack(anchor="w", padx=8, pady=(0, 6))
        self._hint_labels = [h1, h2, h3, h4]

        # 参与窗口自适应宽度计算的控件（日志区可滚动、底部提示自动换行，均不参与）
        self._size_controls = [f1, f2, f3, fb, fh]

    # ---------- 日志/状态 ----------
    def put_log(self, text):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"[{now_str()}] {text}\n")
        line_count = int(self.txt_log.index('end-1c').split('.')[0])
        if line_count > 500:
            self.txt_log.delete("1.0", "200.0")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def set_status(self, text):
        self.status_var.set(text)

    # ---------- 开始/停止 ----------
    def read_cfg_from_ui(self):
        cfg = {}
        for k, e in self.entries.items():
            if k == "procnames":
                cfg[k] = e.get().strip() or DEFAULTS[k]
            else:
                try:
                    cfg[k] = int(e.get().strip())
                except ValueError:
                    cfg[k] = DEFAULTS[k]
        cfg["useright"] = int(self.var_right.get())
        cfg["hotkeys"] = int(self.var_hotkey.get())
        cfg["hotkeystart"] = self.cmb_hotkey_start.get().strip() or DEFAULTS["hotkeystart"]
        cfg["hotkeystop"] = self.cmb_hotkey_stop.get().strip() or DEFAULTS["hotkeystop"]
        cfg["lang"] = CURRENT_LANG   # 语言不在界面读取，保留当前语言，避免保存时被覆盖
        return cfg

    def start_bot(self):
        with shared_lock:
            if shared["running"]:
                return
        cfg = self.read_cfg_from_ui()
        if not (0 <= cfg["vusens"] <= 100):
            messagebox.showwarning(app_title(), T("msg_sens"))
            return
        for k in ("noisedelay", "castdelay", "pulldelay", "timeoutms", "autostopmin", "startdelay"):
            if cfg[k] < 0:
                cfg[k] = 0
        save_config(cfg)
        self.cfg = cfg

        with shared_lock:
            pf = shared["proc_found"]
            sf = shared["sess_found"]
        if not pf:
            messagebox.showwarning(app_title(), T("msg_no_game"))
            return
        if not sf:
            if not messagebox.askyesno(app_title(), T("msg_no_track")):
                return

        evt_stop.clear()
        with shared_lock:
            shared["running"] = True
            shared["fish"] = 0
            shared["cast"] = 0
            shared["elapsed"] = 0
            shared["start_t"] = time.monotonic()
            shared["procnames"] = cfg["procnames"]

        t = threading.Thread(target=bot_thread, args=(cfg,), daemon=True)
        t.start()
        self.threads.append(t)

        self.btn_start.configure(state="disabled", text=T("btn_running"),
                                  fg="#000000", disabledforeground="#A0A0A0")
        self.btn_stop.configure(state="normal", text=self._stop_btn_text())
        for w in self.setting_widgets:
            w.configure(state="disabled")
        self.set_status(T("st_starting_bot"))

    def stop_bot(self):
        with shared_lock:
            if not shared["running"]:
                return
        evt_stop.set()
        self.btn_stop.configure(state="disabled", text=T("btn_stopping"))
        self.set_status(T("st_stopping_bot"))

    def toggle_topmost(self):
        self.root.attributes("-topmost", bool(self.var_top.get()))

    # ---------- 关于窗口 ----------
    def _open_github(self):
        try:
            webbrowser.open("https://github.com/RussDev7/Izzy-s-Ultimate-Fishing-Toolkit")
        except Exception:
            pass

    def show_about(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(T("dlg_about_title"))
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        f = tk.Frame(dlg)
        f.pack(padx=20, pady=14)
        tk.Label(f, text=T("about_author"), font=self.font).pack(anchor="w", pady=2)
        tk.Label(f, text=T("about_cn1"), font=self.font).pack(anchor="w", pady=2)
        tk.Label(f, text=T("about_cn2"), font=self.font).pack(anchor="w", pady=2)
        fb2 = tk.Frame(dlg)
        fb2.pack(pady=(4, 12))
        tk.Button(fb2, text=T("btn_open_github"), font=self.font,
                  command=self._open_github).pack(side="left", padx=8)
        tk.Button(fb2, text=T("btn_close"), font=self.font, command=dlg.destroy).pack(side="left", padx=8)
        # 弹窗居中显示在主窗口上
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

    # ---------- 语言选择窗口 ----------
    def show_language_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(T("dlg_lang_title"))
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        f = tk.Frame(dlg)
        f.pack(padx=14, pady=10)
        for code in LANG_CODES:
            tk.Button(f, text=LANG_NATIVE[code], width=22, font=self.font,
                      command=lambda c=code, d=dlg: self._choose_lang(c, d)).pack(pady=1)
        tk.Button(dlg, text=T("btn_close"), font=self.font, command=dlg.destroy).pack(pady=(4, 10))
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _choose_lang(self, code, dlg):
        if code != CURRENT_LANG:
            self.cfg["lang"] = code
            set_lang(code)
            save_config(self.cfg)
            self.rebuild_ui()
        dlg.destroy()

    def _fit_window(self):
        """按当前语言文本的实际需求自适应窗口大小（语言切换后调用）"""
        if self.root.state() == "zoomed":
            return   # 已最大化，无需调整
        self.root.update_idletasks()
        scale = get_dpi() / 96.0
        min_w = int(540 * scale)
        min_h = int(700 * scale)
        need_w = min_w
        for w in self._size_controls:
            need_w = max(need_w, w.winfo_reqwidth() + 16)
        max_w = int(self.root.winfo_screenwidth() * 0.96)
        max_h = int(self.root.winfo_screenheight() * 0.92)
        new_w = min(need_w, max_w)
        self.root.geometry(f"{new_w}x{min_h}")
        # 底部提示按新宽度自动换行
        for lbl in self._hint_labels:
            lbl.configure(wraplength=max(new_w - 24, 100))
        self.root.update_idletasks()
        need_h = max(self.root.winfo_reqheight(), min_h)
        self.root.geometry(f"{new_w}x{min(need_h, max_h)}")

    def rebuild_ui(self):
        """语言切换后重建整个界面（线程与 shared 状态保持不变）"""
        cur = self.read_cfg_from_ui()                 # 保留用户未保存的编辑
        log_text = self.txt_log.get("1.0", "end-1c")  # 保留运行日志
        for w in self.root.winfo_children():
            w.destroy()
        self._build_ui()
        self.root.title(app_title())
        # 恢复输入框的值
        for k, e in self.entries.items():
            e.delete(0, "end")
            if k == "procnames":
                e.insert(0, cur.get(k, self.cfg.get(k, "")))
            else:
                e.insert(0, str(cur.get(k, self.cfg.get(k, ""))))
        if cur.get("useright"):
            self.chk_right.select()
        else:
            self.chk_right.deselect()
        self.var_hotkey.set(int(cur.get("hotkeys", 1)))
        self.cmb_hotkey_start.set(cur.get("hotkeystart", "F9"))
        self.cmb_hotkey_stop.set(cur.get("hotkeystop", "F10"))
        # 恢复日志
        if log_text:
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", log_text)
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        # 立即按当前运行状态刷新按钮/设置区与状态栏
        with shared_lock:
            running = shared["running"]
        if running:
            for w in self.setting_widgets:
                w.configure(state="disabled")
            self.btn_start.configure(state="disabled", text=T("btn_running"),
                                      fg="#000000", disabledforeground="#A0A0A0")
            self.btn_stop.configure(state="normal", text=self._stop_btn_text())
            self.status_var.set(T("btn_running"))
        else:
            self.btn_stop.configure(state="disabled", text=self._stop_btn_text())
            self.status_var.set(T("st_idle"))
        # 重置界面缓存，让 poll 下一拍全部重新刷新
        self._last = {"proc": -1, "sess": -1, "vu": -1, "fish": -1, "cast": -1,
                      "elapsed": -1, "ui": -1, "hk": None, "status": ""}
        # 窗口自适应到刚好容纳新语言文本的大小
        self._fit_window()

    # ---------- 快捷键同步 ----------
    def _sync_hotkeys(self):
        """把界面上的快捷键设置同步到 shared（热键线程会自动重新注册），有变化时保存"""
        enabled = int(self.var_hotkey.get())
        start_vk = vk_from_name(self.cmb_hotkey_start.get())
        stop_vk = vk_from_name(self.cmb_hotkey_stop.get())
        with shared_lock:
            cur = (bool(shared.get("hotkey_enabled", True)),
                   int(shared.get("hotkey_start_vk", VK_F9)),
                   int(shared.get("hotkey_stop_vk", VK_F10)))
        new = (bool(enabled), start_vk, stop_vk)
        if new != cur:
            with shared_lock:
                shared["hotkey_enabled"] = bool(enabled)
                shared["hotkey_start_vk"] = start_vk
                shared["hotkey_stop_vk"] = stop_vk
            self.cfg["hotkeys"] = enabled
            self.cfg["hotkeystart"] = self.cmb_hotkey_start.get().strip() or DEFAULTS["hotkeystart"]
            self.cfg["hotkeystop"] = self.cmb_hotkey_stop.get().strip() or DEFAULTS["hotkeystop"]
            save_config(self.cfg)

    def _start_btn_text(self):
        with shared_lock:
            enabled = bool(shared.get("hotkey_enabled", True))
            vk = int(shared.get("hotkey_start_vk", VK_F9))
        name = name_from_vk(vk) if enabled else ""
        return T("btn_start_hk", name=name) if name else T("btn_start")

    def _stop_btn_text(self):
        with shared_lock:
            enabled = bool(shared.get("hotkey_enabled", True))
            vk = int(shared.get("hotkey_stop_vk", VK_F10))
        name = name_from_vk(vk) if enabled else ""
        return T("btn_stop_hk", name=name) if name else T("btn_stop")

    # ---------- 主循环轮询（100ms，全部 tkinter 操作都在主线程） ----------
    def poll(self):
        self._sync_hotkeys()
        # 处理工作线程发来的消息
        while True:
            try:
                item = ui_q.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            if kind == "log":
                self.put_log(item[1])
            elif kind == "status":
                self.set_status(item[1])
            elif kind == "alert":
                _, atype, title, text = item
                if atype == "warn":
                    messagebox.showwarning(title, text)
                else:
                    messagebox.showinfo(title, text)
            elif kind == "hotkey_start":
                self.start_bot()
            elif kind == "hotkey_stop":
                self.stop_bot()

        with shared_lock:
            running = shared["running"]
            pf = shared["proc_found"]
            sf = shared["sess_found"]
            vu = shared["vu_pct"]
            fish = shared["fish"]
            cast = shared["cast"]
            start_t = shared["start_t"]
            elapsed = shared["elapsed"]

        L = self._last
        if pf != L["proc"]:
            self.lbl_proc.configure(text=T("st_proc_on") if pf else T("st_proc_off"),
                                    fg="#008C00" if pf else "#C80000")
            L["proc"] = pf
        if sf != L["sess"]:
            self.lbl_sess.configure(text=T("st_sess_on") if sf else T("st_sess_off"),
                                    fg="#008C00" if sf else "#C80000")
            L["sess"] = sf
        if vu != L["vu"]:
            blocks = min(12, int(vu * 12 / 100))
            bar = "█" * blocks + "░" * (12 - blocks)
            self.lbl_vu.configure(text=T("vu_label", bar=bar, vu=vu, thr=self.cfg["vusens"]))
            L["vu"] = vu
        if running:
            elapsed = int(time.monotonic() - start_t)
        if fish != L["fish"] or cast != L["cast"] or elapsed != L["elapsed"]:
            self.stats_var.set(
                T("stats", cast=cast, fish=fish,
                  time=f"{elapsed//3600:02d}:{elapsed//60%60:02d}:{elapsed%60:02d}"))
            L["fish"] = fish
            L["cast"] = cast
            L["elapsed"] = elapsed

        # 按钮与设置区联动
        ui = 1 if running else (0 if pf else 2)
        with shared_lock:
            hk_sig = (bool(shared.get("hotkey_enabled", True)),
                      int(shared.get("hotkey_start_vk", VK_F9)),
                      int(shared.get("hotkey_stop_vk", VK_F10)))
        if ui != L["ui"] or hk_sig != L["hk"]:
            if running:
                self.btn_start.configure(state="disabled", text=T("btn_running"),
                                          fg="#000000", disabledforeground="#A0A0A0")
                self.btn_stop.configure(state="normal", text=self._stop_btn_text())
                for w in self.setting_widgets:
                    w.configure(state="disabled")
            else:
                self.btn_stop.configure(state="disabled", text=self._stop_btn_text())
                for w in self.setting_widgets:
                    w.configure(state="normal")
                if pf:
                    self.btn_start.configure(state="normal", text=self._start_btn_text(),
                                              fg="#008C00", disabledforeground="#A0A0A0")
                else:
                    self.btn_start.configure(state="disabled", text=T("btn_no_game"),
                                              fg="#C80000", disabledforeground="#C80000")
            L["ui"] = ui
            L["hk"] = hk_sig

        self.root.after(100, self.poll)

    # ---------- 退出 ----------
    def on_close(self):
        evt_quit.set()
        evt_stop.set()
        self.cfg = self.read_cfg_from_ui()
        save_config(self.cfg)
        for t in self.threads:
            t.join(timeout=1.0)
        self.root.destroy()

# ============================================================================
# 十、程序入口
# ============================================================================

def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def get_dpi():
    try:
        hdc = user32.GetDC(None)
        if hdc:
            d = gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
            user32.ReleaseDC(None, hdc)
            if d:
                return d
    except Exception:
        pass
    return 96

def main():
    try:
        enable_dpi_awareness()
        dpi = get_dpi()
        scale = dpi / 96.0

        root = tk.Tk()
        try:
            root.tk.call('tk', 'scaling', dpi / 72.0)
        except Exception:
            pass
        W, H = int(540 * scale), int(700 * scale)
        root.geometry(f"{W}x{H}")
        root.minsize(W, H)   # 允许最大化，但不允许缩得比默认布局还小

        App(root)
        root.mainloop()
    except Exception:
        # 用 pythonw/双击 bat 启动时没有控制台，把错误写到文件方便排查
        try:
            import traceback
            log_path = os.path.join(app_dir(), "启动错误日志.txt")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("程序启动失败 / Startup failed，请把本文件内容发给助手：\n\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()
