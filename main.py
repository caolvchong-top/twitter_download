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
    img_format = settings['img_format']
    f.close()

_headers = {
    'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
}
_headers['cookie'] = settings['cookie']

request_count = 0    #请求次数计数
down_count = 0      #下载图片数计数

def del_special_char(string):
    string = re.sub(u'[^\u4e00-\u9fa5\u0030-\u0039\u0041-\u005a\u0061-\u007a\u3040-\u31FF\.]', '', string)
    return string

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
        含图片/视频/音频推数(不含转推):{_user_info.media_count}
        <==================>
        开始爬取...
        '''
    )

def get_download_url(_user_info) -> list:
    def get_url_from_content(content: list) -> list:
        _photo_lst = []
        for i in content:
            try:
                if 'tweet' in i['entryId']:     #正常推文
                    a = i['content']['itemContent']['tweet_results']['result']['legacy']
                    if 'extended_entities' in a and 'retweeted_status_result' not in a:
                        _photo_lst += [_media['media_url_https'] for _media in a['extended_entities']['media']]
                    elif 'retweeted_status_result' in a and has_retweet and 'extended_entities' in a['retweeted_status_result']['result']['legacy']:    #判断是否为转推,以及是否获取转推
                        _photo_lst += [_media['media_url_https'] for _media in a['retweeted_status_result']['result']['legacy']['extended_entities']['media']]
                elif 'profile-conversation' in i['entryId']:    #回复的推文(对话线索)
                    a = i['content']['items'][0]['item']['itemContent']['tweet_results']['result']['legacy']
                    if 'extended_entities' in a:
                        _photo_lst += [_media['media_url_https'] for _media in a['extended_entities']['media']]
            except Exception:
                continue
            if 'cursor-bottom' in i['entryId']:     #更新下一页的请求编号
                _user_info.cursor = i['content']['value']
        for i in _photo_lst[::]:        #排除掉视频等其它的封面图片
            if 'https://pbs.twimg.com/media/' not in i:
                _photo_lst.remove(i)
        return _photo_lst

    print(f'已下载图片:{_user_info.count}')
    url_top = 'https://twitter.com/i/api/graphql/2GIWTr7XwadIixZDtyXd4A/UserTweets?variables={"userId":"' + _user_info.rest_id + '","count":20,'
    url_bottom = '"includePromotedContent":false,"withQuickPromoteEligibilityTweetFields":true,"withVoice":true,"withV2Timeline":true}&features={"rweb_lists_timeline_redesign_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":false,"tweet_awards_web_tipping_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_media_download_video_enabled":false,"responsive_web_enhance_cards_enabled":false}&fieldToggles={"withAuxiliaryUserLabels":false,"withArticleRichContentState":false}'
    if _user_info.cursor:
        url = url_top + '"cursor":"' + _user_info.cursor + '",' + url_bottom
    else:
        url = url_top + url_bottom      #第一页,无cursor
    try:
        global request_count
        response = httpx.get(url, headers=_headers).text
        request_count += 1
        raw_data = json.loads(response)
        raw_data = raw_data['data']['user']['result']['timeline_v2']['timeline']['instructions'][-1]['entries']
        if 'cursor-top' in raw_data[0]['entryId']:      #所有推文已全部下载完成
            return False
        photo_lst = get_url_from_content(raw_data)
        if not photo_lst:
            photo_lst.append(True)
    except Exception:
        print('获取推文信息错误')
        print(response)
        return False
    return photo_lst

def download_control(_user_info):
    async def _main():
        async def down_save(url, order: int):
            re_rule = 'media/(.*?)\.[jpg|png]{3}'
            file_name = re.findall(re_rule,url)[0]      #不含后缀
            url += f'?format={img_format}&name=4096x4096'
            while True:
                try:
                    async with httpx.AsyncClient() as client:
                        global down_count
                        response = await client.get(url)
                        down_count += 1
                    with open(f'{_user_info.save_path + os.sep}{_user_info.count + order}_{file_name}.{img_format}','wb') as f:
                        f.write(response.content)
                    if log_output:
                        print(f'{file_name}=====>下载完成')
                    break
                except Exception:
                    print(f'{file_name}=====>下载失败,重试')
                    print(url)

        while True:
            photo_lst = get_download_url(_user_info)
            if not photo_lst:
                break
            elif photo_lst[0] == True:
                continue
            await asyncio.gather(*[asyncio.create_task(down_save(url,order)) for order,url in enumerate(photo_lst)])
            _user_info.count += len(photo_lst)      #更新计数

    asyncio.run(_main())

def main(_user_info: object):
    re_token = 'ct0=(.*?);'
    _headers['x-csrf-token'] = re.findall(re_token,_headers['cookie'])[0]
    _headers['referer'] = 'https://twitter.com/' + _user_info.screen_name
    if not get_other_info(_user_info):
        return False
    print_info(_user_info)
    _path = settings['save_path']+del_special_char(_user_info.name)
    if not os.path.exists(_path):   #创建文件夹
        try:
            os.makedirs(_path)      #优先尝试用昵称建文件夹(仅限中英日或数字)
            _user_info.save_path = _path
        except Exception:
            os.makedirs(settings['save_path']+_user_info.screen_name)       #不行就用用户名建文件夹
            _user_info.save_path = settings['save_path']+_user_info.screen_name
    else:
        _user_info.save_path = _path
    download_control(_user_info)
    print(f'{_user_info.name}下载完成\n\n')

if __name__=='__main__':
    _start = time.time()
    for i in settings['user_lst'].split(','):
        main(User_info(i))
    print(f'共耗时:{time.time()-_start}秒\n共调用{request_count}次API\n共下载{down_count}张图片')
