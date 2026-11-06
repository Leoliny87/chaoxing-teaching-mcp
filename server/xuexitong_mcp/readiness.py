"""Passive, bounded bootstrap readiness; never repeats a failed browser command."""
from pathlib import Path
import re
import tempfile
import time

def wait_observation_ready(browser, course_name=None, *, samples=8, interval=1.0):
    """Require the requested observed course and two identical complete replies.

    This is an application readiness check, not authorization or proof of future
    stability. All subsequent actions still use normal BrowserSkill guards.
    Any browser error escapes immediately, without another sync or navigation.
    """
    from xuexitong_mcp.bsk import BskError
    if not isinstance(browser.tab,int) or not isinstance(browser.session,str):
        raise BskError('readiness_missing_owner','无法确认本次任务标签，停止。')
    if course_name is not None and (not isinstance(course_name,str) or not course_name):
        raise BskError('readiness_missing_target','就绪观察需要确切课程名称。')
    previous_text=None
    reports=[]
    browser.readiness_report=reports
    # Actual portal observation: heading/link "测试课程 置顶". The badges are
    # display text, not part of the course name; accept only observed badges.
    title=re.compile(r'\b(?:heading|link)\s+"'+re.escape(course_name)+r'(?:\s+(?:置顶|已结课))*"') if course_name is not None else None
    with tempfile.TemporaryDirectory(prefix='xxt-bootstrap-readiness-') as tmp:
        predecessor=None
        for index in range(samples):
            current=Path(tmp)/f'{index}.json'
            args=['cooperate','sync','--tab-id',str(browser.tab),'--save-full',str(current)]
            if predecessor is not None:
                args+=['--baseline',str(predecessor)]
            data=browser.run(args)
            state=data.get('state') or {}
            if (data.get('tab_id')!=browser.tab or state.get('mode')!='ready'
                    or data.get('ready') is False or state.get('editing') or data.get('activity')
                    or not isinstance(data.get('context_id'),str) or not data['context_id']
                    or not isinstance(data.get('observation_id'),str) or not data['observation_id']):
                raise BskError('readiness_control_uncertain','观察时控制未就绪或用户正在操作，停止。')
            observation=data.get('observation') or {}
            text=observation.get('text')
            if (not isinstance(text,str) or not text or observation.get('truncated') is not False
                    or observation.get('capture_truncated') or observation.get('next_cursor') or data.get('next_cursor')):
                raise BskError('readiness_observation_incomplete','未取得完整当前观察，停止而不猜测。')
            target_seen=bool(title.search(text)) if title is not None else True
            stable=target_seen and previous_text==text
            reports.append({'sample':index+1,'text_chars':len(text),'target_seen':target_seen if title is not None else None,
                            'same_as_previous':previous_text==text,'mode':state['mode'],
                            'revision':state.get('revision'),'kind':data.get('kind')})
            if stable:
                browser.obs_text=''  # Subsequent actions must obtain their own current receipt.
                return reports
            previous_text=text if target_seen else None
            # Only use a file actually saved by the normal CLI on this call.
            if not current.is_file():
                raise BskError('readiness_receipt_missing','同步完整回执没有保存，停止。')
            predecessor=current
            if index+1<samples:time.sleep(interval)
    raise BskError('readiness_timeout','限定次数内目标内容未出现或持续变化；已停止后续页面动作。',
                   {'readiness_samples':reports})


def wait_homepage_course_ready(browser, course_name, **kwargs):
    return wait_observation_ready(browser, course_name, **kwargs)
