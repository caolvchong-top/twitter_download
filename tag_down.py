import httpx

import asyncio
import re
import os
import time
import json
import hashlib
from urllib.parse import quote_plus



##########配置区域##########
cookie = 'auth_token=xxxxxxxxxxx; ct0=xxxxxxxxxxx;'
# 填入 cookie (auth_token与ct0字段) //重要:替换掉其中的x即可, 注意不要删掉分号

tag = '#ヨルクラ'
# 填入tag 带上#号

down_count = 400
# 因为搜索结果数量可能极大，故手动确定下载总量，填200的倍数，最少200

##########配置区域##########



def del_special_char(string):
    string = re.sub(u'[^#\u4e00-\u9fa5\u0030-\u0039\u0041-\u005a\u0061-\u007a\u3040-\u31FF\.]', '', string)
    return string

def stamp2time(msecs_stamp:int) -> str:
    timeArray = time.localtime(msecs_stamp/1000)
    otherStyleTime = time.strftime("%Y-%m-%d", timeArray)
    return otherStyleTime

def hash_save_token(media_url):
    m = hashlib.md5()
    m.update(f'{media_url}'.encode('utf-8'))
    return m.hexdigest()[:4]


def get_heighest_video_quality(variants) -> str:   #找到最高质量的视频地址,并返回

        if len(variants) == 1:      #gif适配
            return variants[0]['url']
        
        max_bitrate = 0
        heighest_url = None
        for i in variants:
            if 'bitrate' in i:
                if int(i['bitrate']) > max_bitrate:
                    max_bitrate = int(i['bitrate'])
                    heighest_url = i['url']
        return heighest_url

def download_control(folder_path, photo_lst):
    async def _main():
        async def down_save(url, folder_path, time_stamp, user_name):
            if '.mp4' in url:
                _file_name = f'{folder_path}{stamp2time(time_stamp)}_{user_name}_{hash_save_token(url)}.mp4'
            else:
                try:
                    _file_name = f'{folder_path}{stamp2time(time_stamp)}_{user_name}_{hash_save_token(url)}.png'
                    url += '?format=png&name=4096x4096'
                except Exception as e:
                    print(e)
                    return False
            count = 0
            while True:
                try:
                    async with semaphore:
                        async with httpx.AsyncClient() as client:
                            response = await client.get(url, timeout=(3.05, 16))        #如果出现第五次或以上的下载失败,且确认不是网络问题,可以适当降低最大并发数量
                    with open(_file_name,'wb') as f:
                        f.write(response.content)
                    break
                except Exception as e:
                    count += 1
                    print(e)
                    print(f'{_file_name}=====>第{count}次下载失败,正在重试')
                    input(url)

        semaphore = asyncio.Semaphore(8)
        await asyncio.gather(*[asyncio.create_task(down_save(url[0], folder_path, url[1], url[2])) for url in photo_lst])   #0:url 1:time_stamp 2:user_name

    asyncio.run(_main())

class tag_down():
    def __init__(self):

        self.folder_path = os.getcwd() + os.sep + del_special_char(tag) + os.sep

        if not os.path.exists(self.folder_path):   #创建文件夹
            os.makedirs(self.folder_path)

        self._headers = {
            'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        }
        self._headers['cookie'] = cookie
        re_token = 'ct0=(.*?);'
        self._headers['x-csrf-token'] = re.findall(re_token, cookie)[0]
        self._headers['referer'] = f'https://twitter.com/search?q={quote_plus(tag)}&src=typed_query&f=media'

        self.cursor = ''

        for i in range(down_count//200):
            url = 'https://twitter.com/i/api/graphql/5yhbMCF0-WQ6M8UOAs1mAg/SearchTimeline?variables={"rawQuery":"' + quote_plus(tag) + '","count":200,"cursor":"' + self.cursor + '","querySource":"typed_query","product":"Media"}&features={"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"articles_preview_enabled":true,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"tweet_with_visibility_results_prefer_gql_media_interstitial_enabled":true,"rweb_video_timestamps_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_enhance_cards_enabled":false}'

            media_lst = self.search(url)
            if not media_lst:
                return
            download_control(self.folder_path, media_lst)

    def search(self, url):
        #接收某页链接，返回该页所有图片地址
        media_lst = []

        response = httpx.get(url, headers=self._headers).text
        raw_data = json.loads(response)
        if not self.cursor: #第一次
            raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions'][-1]['entries']
            if len(raw_data) == 2:
                return
            self.cursor = raw_data[-1]['content']['value']
            raw_data_lst = raw_data[0]['content']['items']
        else:
            raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions']
            self.cursor = raw_data[-1]['entry']['content']['value']
            raw_data_lst = raw_data[0]['moduleItems']
            
        for tweet in raw_data_lst:
            tweet = tweet['item']['itemContent']['tweet_results']['result']
            screen_name = '@' + tweet['core']['user_results']['result']['legacy']['screen_name']
            time_stamp = int(tweet['edit_control']['editable_until_msecs'])
            raw_media_lst = tweet['legacy']['extended_entities']['media']
            for _media in raw_media_lst:
                if 'video_info' in _media:
                    media_url = get_heighest_video_quality(_media['video_info']['variants'])
                else:
                    media_url = _media['media_url_https']
                media_lst.append([media_url, time_stamp, screen_name])
        return media_lst


if __name__ == '__main__':
    print('无过程输出...(๑´ڡ`๑)')
    tag_down()
    print('已完成')
