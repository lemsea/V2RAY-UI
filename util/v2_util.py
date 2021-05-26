import atexit
import codecs
import collections
import json
import logging
import os
import platform
import re
import subprocess
import sys
from collections import deque
from enum import Enum
from threading import Timer, Lock
from typing import Optional

import psutil

from util import config, list_util, cmd_util, file_util, json_util, sys_util
from v2ray.models import Inbound


def get_xray_file_name():
    return f'xray-v2-ui-{sys_util.sys_name()}-{sys_util.arch()}'


V2_CONF_KEYS = ['log', 'api', 'dns', 'routing', 'policy', 'inbounds', 'outbounds', 'transport',
                'stats', 'reverse']
__is_windows: bool = sys_util.is_windows()
__v2ray_cmd: str = os.path.join(config.BASE_DIR, 'bin', get_xray_file_name())
__v2ray_conf_path: str = os.path.join(config.BASE_DIR, 'bin', 'config.json')
__v2ray_process: Optional[subprocess.Popen] = None
__v2ray_error_msg: str = ''
__v2ray_version: str = ''
__v2ray_process_lock: Lock = Lock()


class Protocols(Enum):
    VMESS = 'vmess'
    SHADOWSOCKS = 'shadowsocks'
    DOKODEMO = 'dokodemo-door'
    SOCKS = 'socks'
    HTTP = 'http'


def start_v2ray():
    global __v2ray_process, __v2ray_error_msg
    encoding = 'gbk' if __is_windows else 'utf-8'
    __v2ray_process = subprocess.Popen([__v2ray_cmd, '-config', __v2ray_conf_path], shell=False,
                                       stderr=subprocess.STDOUT, stdout=subprocess.PIPE, encoding=encoding)
    logging.info('start xray')

    def f():
        global __v2ray_error_msg
        p = __v2ray_process
        last_lines: collections.deque = deque()
        try:
            while p.poll() is None:
                line = p.stdout.readline()
                if not line:
                    break
                if len(last_lines) >= 10:
                    last_lines.popleft()
                last_lines.append(line)
        except Exception as ex:
            logging.warning(ex)
        finally:
            __v2ray_error_msg = '\n'.join(last_lines)

    __v2ray_error_msg = ''
    Timer(0, f).start()


def stop_v2ray():
    global __v2ray_process
    if __is_windows:
        for p in psutil.process_iter():
            if 'xray.exe' in p.name():
                p.terminate()
    if __v2ray_process is not None:
        try:
            __v2ray_process.terminate()
            logging.info('stop xray')
        except Exception as e:
            logging.warning(f'stop xray error: {e}')
        finally:
            __v2ray_process = None


def restart_v2ray():
    with __v2ray_process_lock:
        stop_v2ray()
        start_v2ray()


def gen_v2_config_from_db():
    inbounds = Inbound.query.filter_by(enable=True).all()
    inbounds = [inbound.to_v2_json() for inbound in inbounds]
    v2_config = json.loads(config.get_v2_template_config())
    v2_config['inbounds'] += inbounds
    for conf_key in V2_CONF_KEYS:
        if conf_key not in v2_config:
            v2_config[conf_key] = {}
    return v2_config


def read_v2_config() -> Optional[dict]:
    try:
        # path = config.get_v2_config_path()
        # file_util.touch(path)
        # with open(path, encoding='utf-8') as f:
        #     return f.read()
        content = file_util.read_file(__v2ray_conf_path)
        return json.loads(content)

        # conf_path = '/usr/local/etc/v2ray/'
        # files: List[str] = file_util.list_files(conf_path)
        # v2_config: dict = {}
        # for file_name in files:
        #     content: str = file_util.read_file(f'{conf_path}{file_name}')
        #     for conf_key in V2_CONF_KEYS:
        #         if conf_key in file_name:
        #             conf: dict = json.loads(content)
        #             if conf_key in ['inbounds', 'outbounds']:
        #                 conf.setdefault(conf_key, [])
        #             else:
        #                 conf.setdefault(conf_key, {})
        #             v2_config[conf_key] = conf[conf_key]
        #             break
        # return v2_config
    except Exception as e:
        logging.error('An error occurred while reading the xray configuration file: ' + str(e))
        return None


def write_v2_config(v2_config: dict):
    # v2_config: str = json.dumps(v2_config, ensure_ascii=False, sort_keys=True, indent=2, separators=(',', ': '))
    if read_v2_config() == v2_config:
        return
    try:
        file_util.write_file(__v2ray_conf_path, json_util.dumps(v2_config))
        # conf_path = '/usr/local/etc/v2ray/'
        # files: List[str] = file_util.list_files(conf_path)
        # for file_name in files:
        #     for conf_key in V2_CONF_KEYS:
        #         if conf_key in file_name:
        #             try:
        #                 conf: dict = {
        #                     conf_key: v2_config[conf_key]
        #                 }
        #                 content: str = json_util.dumps(conf)
        #                 file_util.write_file(f'{conf_path}{file_name}', content)
        #             except Exception as e:
        #                 logging.error(f'An error occurred while writing the v2ray configuration file({file_name}): {e}')
        #             break
        restart(True)
    except Exception as e:
        logging.error('An error occurred while writing the xray configuration file: ' + str(e))


def __get_api_address_port():
    template_config = json.loads(config.get_v2_template_config())
    inbounds = template_config['inbounds']
    api_inbound = list_util.get(inbounds, 'tag', 'api')
    return api_inbound['listen'], api_inbound['port']


def __get_stat_code():
    if __v2ray_process is None or __v2ray_process.poll() is not None:
        if __v2ray_error_msg != '':
            return 2
        return 1
    return 0


def get_v2ray_version():
    global __v2ray_version
    if __v2ray_version != '':
        return __v2ray_version
    result, code = cmd_util.exec_cmd(f'{__v2ray_cmd} -version')
    if code != 0:
        return 'Unknown'
    else:
        try:
            __v2ray_version = result.split(' ')[1]
            return __v2ray_version
        except Exception as e:
            logging.warning(f'get xray version failed: {e}')
            return 'Error'


def get_v2ray_error_msg():
    return __v2ray_error_msg


def is_running():
    return __get_stat_code() == 0


def restart(now=False):
    def f():
        try:
            restart_v2ray()
        except Exception as e:
            logging.warning(f'restart xray error: {e}')

    if now:
        f()
    else:
        Timer(3, f).start()


try:
    __api_address, __api_port = __get_api_address_port()
    if not __api_address or __api_address == '0.0.0.0':
        __api_address = '127.0.0.1'
except Exception as e:
    logging.error('Fail to open xray api, please reset all panel settings.')
    logging.error(str(e))
    sys.exit(-1)
__traffic_pattern = re.compile('stat:\s*<\s*name:\s*"inbound>>>'
                               '(?P<tag>[^>]+)>>>traffic>>>(?P<type>uplink|downlink)"(\s*value:\s*(?P<value>\d+))?')


def __get_v2ray_api_cmd(address, pattern, reset):
    cmd = '%s api statsquery --server=%s:%d -pattern "%s" %s' \
          % (__v2ray_cmd, address, __api_port, pattern, reset)
    return cmd


def get_inbounds_traffic(reset=True):
    if __api_port < 0:
        logging.warning('xray api port is not configured')
        return None
    cmd = __get_v2ray_api_cmd('127.0.0.1', '', '-reset' if reset else 'false')
    result, code = cmd_util.exec_cmd(cmd)
    if code != 0:
        logging.warning('xray api code %d' % code)
        return None
    inbounds = []
    try:
        name_pattern = re.compile("inbound>>>(?P<tag>[^>]+)>>>traffic>>>(?P<type>uplink|downlink)")
        stat = json.loads(result)
        stats = stat["stat"]
        for s in stats:
            name = s["name"]
            value = 0
            if "value" in s:
                value = s["value"]
            match = name_pattern.fullmatch(name)
            tag = match.group("tag")
            tag = codecs.getdecoder('unicode_escape')(tag)[0]
            tag = tag.encode('ISO8859-1').decode('utf-8')
            if tag == 'api':
                continue
            _type = match.group('type')
            inbound = list_util.get(inbounds, 'tag', tag)
            if inbound:
                inbound[_type] = value
            else:
                inbounds.append({
                    'tag': tag,
                    _type: value
                })
    except Exception as e:
        logging.error(e)
    # for match in __traffic_pattern.finditer(result):
    #     tag = match.group('tag')
    #     tag = codecs.getdecoder('unicode_escape')(tag)[0]
    #     tag = tag.encode('ISO8859-1').decode('utf-8')
    #     if tag == 'api':
    #         continue
    #     _type = match.group('type')
    #     value = match.group('value')
    #     if not value:
    #         value = 0
    #     else:
    #         value = int(value)
    #     inbound = list_util.get(inbounds, 'tag', tag)
    #     if inbound:
    #         inbound[_type] = value
    #     else:
    #         inbounds.append({
    #             'tag': tag,
    #             _type: value
    #         })
    return inbounds


def init_v2ray():
    file_util.write_file(__v2ray_conf_path, '{}')
    v2_config = gen_v2_config_from_db()
    write_v2_config(v2_config)


@atexit.register
def on_exit():
    stop_v2ray()
