import re
import time
import httpx
import asyncio
import os
import json
from user_info import User_info

#读取配置
log_output = False
has_retweet = False
with open('settings.json', 'r', encoding='utf8') as f:
    settings = json.load(f)
    if not settings['save_path']:
        settings['save_path'] = os.getcwd()
    settings['save_path'] += os.sep
    if settings['has_retweet']:
        has_retweet = True
    if settings['log_output']:
        log_output = True
    f.close()

_headers = {
    'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
}
_headers['cookie'] = settings['cookie']

request_count = 0    #请求次数计数
down_count = 0      #下载图片数计数

def get_other_info(_user_info):
    url = 'https://twitter.com/i/api/graphql/xc8f1g7BYqr6VTzTbvNlGw/UserByScreenName?variables={"screen_name":"' + _user_info.screen_name + '","withSafetyModeUserFields":false}&features={"hidden_profile_likes_enabled":false,"hidden_profile_subscriptions_enabled":false,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"subscriptions_verification_info_verified_since_enabled":true,"highlights_tweets_tab_ui_enabled":true,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}&fieldToggles={"withAuxiliaryUserLabels":false}'
    try:
        global request_count
        response = httpx.get(url, headers=_headers).text
        request_count += 1
        raw_data = json.loads(response)
        _user_info.rest_id = raw_data['data']['user']['result']['rest_id']
        _user_info.name = raw_data['data']['user']['result']['legacy']['name']
        _user_info.statuses_count = raw_data['data']['user']['result']['legacy']['statuses_count']
        _user_info.media_count = raw_data['data']['user']['result']['legacy']['media_count']
    except Exception:
        print('获取信息失败')
        print(response)
        return False
    return True

def print_info(_user_info):
    print(
        f'''
        <======基本信息=====>
        昵称:{_user_info.name}
        用户名:{_user_info.screen_name}
        数字ID:{_user_info.rest_id}
        总推数(含转推):{_user_info.statuses_count}
        含图片/视频推数(不含转推):{_user_info.media_count}
        
        开始爬取...
        '''
    )

def download_control(_user_info):
    pass

def main(_user_info: object):
    re_token = 'ct0=(.*?);'
    print(_user_info.screen_name)
    _headers['x-csrf-token'] = re.findall(re_token,_headers['cookie'])[0]
    _headers['referer'] = 'https://twitter.com/' + _user_info.screen_name
    if not get_other_info(_user_info):
        return False
    print_info(_user_info)
    download_control(_user_info)

    pass


if __name__=='__main__':
    _start = time.time()
    for i in settings['user_lst'].split(','):
        main(User_info(i))
        input('暂停...')
    print(f'共耗时:{time.time()-_start}秒\n共调用{request_count}次API\n共下载{down_count}张图片')
