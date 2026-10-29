import ctypes
from ctypes import wintypes
import logging
import os
import sys
from typing import Optional, Tuple
import keyring

logger = logging.getLogger(__name__)

# Windows 외 OS(macOS 등)에서는 Credential Manager 대신 keyring만 사용
advapi32 = ctypes.windll.advapi32 if sys.platform == "win32" else None
kernel32 = ctypes.windll.kernel32 if sys.platform == "win32" else None

class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD),
        ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR),
        ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME),
        ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(ctypes.c_byte)),
        ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD),
        ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR),
        ('UserName', wintypes.LPWSTR),
    ]

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2

def get_windows_credential(target_name: str = "wiki.example.com") -> Tuple[Optional[str], Optional[str]]:
    """Windows Credential Manager(일반 자격 증명)에서 계정명과 비밀번호를 안전하게 조회"""
    # 1. keyring 시도
    # 등록된 사용자명 찾기
    pcred = ctypes.POINTER(CREDENTIALW)()
    res = advapi32 and advapi32.CredReadW(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred))
    if res:
        username = pcred.contents.UserName
        blob_size = pcred.contents.CredentialBlobSize
        password = None
        if blob_size > 0 and pcred.contents.CredentialBlob:
            raw_bytes = ctypes.string_at(pcred.contents.CredentialBlob, blob_size)
            # UTF-16LE or UTF-8 decoding
            try:
                password = raw_bytes.decode('utf-16le')
            except UnicodeDecodeError:
                password = raw_bytes.decode('utf-8', errors='ignore')
        advapi32.CredFree(pcred)
        if username and password:
            logger.info(f"Windows 자격 증명 관리자에서 '{target_name}' 일반 자격 증명 로드 성공 (사용자: {username})")
            return username, password

    # 2. keyring 라이브러리 fallback
    try:
        # .env의 CONFLUENCE_EMAIL(또는 @ 앞 아이디)로 등록되어 있는지 확인
        email = os.getenv("CONFLUENCE_EMAIL", "")
        for uname in filter(None, [email, email.split("@")[0]]):
            pwd = keyring.get_password(target_name, uname)
            if pwd:
                logger.info(f"Keyring에서 '{target_name}' 자격 증명 로드 성공 (사용자: {uname})")
                return uname, pwd
    except Exception as e:
        logger.debug(f"keyring 조회 실패: {e}")

    return None, None

def save_windows_credential(target_name: str, username: str, password: str) -> bool:
    """Windows Credential Manager(일반 자격 증명)에 안전하게 암호화 보관"""
    try:
        keyring.set_password(target_name, username, password)
        logger.info(f"Windows 자격 증명 관리자에 '{target_name}' 저장 완료 (사용자: {username})")
        return True
    except Exception as e:
        logger.error(f"Windows 자격 증명 저장 실패: {e}")
        return False
