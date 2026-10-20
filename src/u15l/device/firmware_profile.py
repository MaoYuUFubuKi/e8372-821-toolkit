"""Prepared firmware identity. Unrendered source never authorizes a candidate."""
import json

PROFILE_JSON = '__FIRMWARE_PROFILE_JSON__'
PROFILE = None if PROFILE_JSON.startswith('__') else json.loads(PROFILE_JSON)


def require_profile():
    if PROFILE is None:
        raise RuntimeError('固件配置尚未由 prepare 绑定，禁止生成或刷写候选。')
    return PROFILE
