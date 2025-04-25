import httpx

import asyncio
import re
import os
import csv
import time
import json
import hashlib
from datetime import datetime
from urllib.parse import quote
from url_utils import quote_url
from transaction_generate import get_url_path
from transaction_generate import get_transaction_id


##########配置区域##########

cookie = 'auth_token=xxxxxxxxxxx; ct0=xxxxxxxxxxx;'
# 填入 cookie (auth_token与ct0字段) //重要:替换掉其中的x即可, 注意不要删掉分号

tag = '#ヨルクラ'
# 填入tag 带上#号 可留空
_filter = ""
# (可选项) 高级搜索
# 请在 https://x.com/search-advanced 中组装搜索条件，复制搜索栏的内容填入_filter
# 注意，_filter中所有出现的双引号都需要改为单引号或添加转义符 例如 "Monika" -> 'Monika'

# ↑↑ 当tag选项留空时，将尝试以_filter的内容作为文件夹名称

down_count = 100
# 因为搜索结果数量可能极大，故手动确定下载总量(近似)，填50的倍数，最少50

media_latest = False
# media_latest为True时，对应 [最新] 标签页，False对应 [媒体] 标签页 (与文本模式无关)
# 开启时建议 _filter 设置为 _filter = 'filter:links -filter:replies'

# ------------------------ #

text_down = False
# 开启后变为文本下载模式，会消耗大量API次数
# 开启文本下载时 不要包含 filter:links

##########配置区域##########

max_concurrent_requests = 8     #最大并发数量，默认为8，遇到多次下载失败时适当降低

if text_down:
    entries_count = 20
    product = 'Latest'
    mode = 'text'
else:
    entries_count = 50
    product = 'Media'
    mode = 'media'
    if media_latest:
        entries_count = 20
        product = 'Latest'
        mode = 'media_latest'
_filter = ' ' + _filter



def del_special_char(string):
    string = re.sub(r'[^#\u4e00-\u9fa5\u0030-\u0039\u0041-\u005a\u0061-\u007a\u3040-\u31FF\.]', '', string)
    return string

def stamp2time(msecs_stamp:int) -> str:
    timeArray = time.localtime(msecs_stamp/1000)
    otherStyleTime = time.strftime("%Y-%m-%d %H-%M", timeArray)
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

def download_control(media_lst, _csv):
    async def _main():
        async def down_save(url, _csv_info, is_image):
            if is_image:
                url += '?format=png&name=4096x4096'

            count = 0
            while True:
                try:
                    async with semaphore:
                        async with httpx.AsyncClient() as client:
                            response = await client.get(quote_url(url), timeout=(3.05, 16))        #如果出现第五次或以上的下载失败,且确认不是网络问题,可以适当降低最大并发数量
                    with open(_csv_info[6],'wb') as f:  #_csv_info[6] : Saved Path
                        f.write(response.content)
                    break
                except Exception as e:
                    count += 1
                    print(e)
                    print(f'{_csv_info[6]}=====>第{count}次下载失败,正在重试')
            _csv.data_input(_csv_info)

        semaphore = asyncio.Semaphore(max_concurrent_requests)
        await asyncio.gather(*[asyncio.create_task(down_save(url[0], url[1], url[2])) for url in media_lst])   # 0:url 1:csv_info 2:is_image

    asyncio.run(_main())

class csv_gen():
    def __init__(self, save_path:str) -> None:
        self.f = open(f'{save_path}/{datetime.now().strftime("%Y-%m-%d %H-%M-%S")}-{mode}.csv', 'w', encoding='utf-8-sig', newline='')
        self.writer = csv.writer(self.f)

        #初始化
        self.writer.writerow(['Run Time : ' + datetime.now().strftime('%Y-%m-%d %H-%M-%S')])
        if text_down:
            main_par = ['Tweet Date', 'Display Name', 'User Name', 'Tweet URL', 'Tweet Content', 'Favorite Count', 
                        'Retweet Count', 'Reply Count']
        else:   #media格式
            main_par = ['Tweet Date', 'Display Name', 'User Name', 'Tweet URL', 'Media Type', 'Media URL', 'Saved Path', 'Tweet Content', 'Favorite Count', 
                        'Retweet Count', 'Reply Count']
        self.writer.writerow(main_par)

    def csv_close(self):
        self.f.close()

    def stamp2time(self, msecs_stamp:int) -> str:
        timeArray = time.localtime(msecs_stamp/1000)
        otherStyleTime = time.strftime("%Y-%m-%d %H:%M", timeArray)
        return otherStyleTime
    
    def data_input(self, main_par_info:list) -> None:   #数据格式参见 main_par
        main_par_info[0] = self.stamp2time(main_par_info[0])    #传进来的是 int 时间戳, 故转换一下
        self.writer.writerow(main_par_info)

class tag_down():
    def __init__(self):
        if tag:
            self.folder_path = os.getcwd() + os.sep + del_special_char(tag) + os.sep
        else:
            self.folder_path = os.getcwd() + os.sep + del_special_char(_filter) + os.sep

        if not os.path.exists(self.folder_path):   #创建文件夹
            os.makedirs(self.folder_path)

        self.csv = csv_gen(self.folder_path)

        self._headers = {
            'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        }
        self._headers['cookie'] = cookie
        re_token = 'ct0=(.*?);'
        self._headers['x-csrf-token'] = re.findall(re_token, cookie)[0]
        self._headers['referer'] = f'https://twitter.com/search?q={quote(tag + _filter)}&src=typed_query&f=media'

        self.cursor = ''

        self.ct = get_transaction_id()

        for i in range(down_count//entries_count):
            url = 'https://x.com/i/api/graphql/AIdc203rPpK_k_2KWSdm7g/SearchTimeline?variables={"rawQuery":"' + quote(tag + _filter) + '","count":' + str(entries_count) + ',"cursor":"' + self.cursor + '","querySource":"typed_query","product":"' + product + '"}&features={"rweb_video_screen_enabled":false,"profile_label_improvements_pcf_label_in_post_enabled":true,"rweb_tipjar_consumption_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":true,"responsive_web_jetfuel_frame":false,"responsive_web_grok_share_attachment_enabled":true,"articles_preview_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"responsive_web_grok_show_grok_translated_post":false,"responsive_web_grok_analysis_button_from_backend":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_enhance_cards_enabled":false}'
            _path = get_url_path(url)
            url = quote_url(url)
            self._headers['x-client-transaction-id'] = self.ct.generate_transaction_id(method='GET', path=_path)
            if text_down:
                if not self.search_save_text(url):
                    break
            else:
                if media_latest:
                    media_lst = self.search_media_latest(url)
                else:
                    media_lst = self.search_media(url)
                if not media_lst:
                    return
                download_control(media_lst, self.csv)

        self.csv.csv_close()

    def search_media(self, url):
        #接收某页链接，返回该页所有图片地址
        media_lst = []

        response = httpx.get(url, headers=self._headers).text
        try:
            raw_data = json.loads(response)
        except Exception:
            if 'Rate limit exceeded' in response:
                print('API次数已超限')
            else:
                print('获取数据失败')
            print(response)
            return
        if not self.cursor: #第一次
            raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions'][-1]['entries']
            if len(raw_data) == 2:
                return
            self.cursor = raw_data[-1]['content']['value']
            raw_data_lst = raw_data[0]['content']['items']
        else:
            raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions']
            self.cursor = raw_data[-1]['entry']['content']['value']
            if 'moduleItems' in raw_data[0]:
                raw_data_lst = raw_data[0]['moduleItems']
            else:
                return

        for tweet in raw_data_lst:
            tweet = tweet['item']['itemContent']['tweet_results']['result']
            try:
                display_name = tweet['core']['user_results']['result']['legacy']['name']
                screen_name = '@' + tweet['core']['user_results']['result']['legacy']['screen_name']
            except Exception:   #低概率事件
                continue
            try:
                time_stamp = int(tweet['edit_control']['editable_until_msecs']) - 3600000
            except Exception as e:
                if 'edit_control_initial' in tweet['edit_control']:
                    time_stamp = int(tweet['edit_control']['edit_control_initial']['editable_until_msecs']) - 3600000
                else:
                    continue
            try:
                Favorite_Count = tweet['legacy']['favorite_count']
                Retweet_Count = tweet['legacy']['retweet_count']
                Reply_Count = tweet['legacy']['reply_count']
                _status_id = tweet['legacy']['conversation_id_str']
                tweet_url = f'https://twitter.com/{screen_name}/status/{_status_id}'
                tweet_content = tweet['legacy']['full_text'].split('https://t.co/')[0]
            except Exception as e:
                print(e)
                continue
            try:
                raw_media_lst = tweet['legacy']['extended_entities']['media']
                for _media in raw_media_lst:
                    if 'video_info' in _media:
                        media_url = get_heighest_video_quality(_media['video_info']['variants'])
                        media_type = 'Video'
                        is_image = False
                        _file_name = f'{self.folder_path}{stamp2time(time_stamp)}_{screen_name}_{hash_save_token(media_url)}.mp4'
                    else:
                        media_url = _media['media_url_https']
                        media_type = 'Image'
                        is_image = True
                        _file_name = f'{self.folder_path}{stamp2time(time_stamp)}_{screen_name}_{hash_save_token(media_url)}.png'

                    media_csv_info = [time_stamp, display_name, screen_name, tweet_url, media_type, media_url, _file_name, tweet_content, Favorite_Count, Retweet_Count, Reply_Count]
                    media_lst.append([media_url, media_csv_info, is_image])
            except Exception as e:
                print(e)
                continue
        return media_lst
    
    def search_media_latest(self, url):
        media_lst = []

        response = httpx.get(url, headers=self._headers).text
        raw_data = json.loads(response)
        if not self.cursor: #第一次
            raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions'][-1]['entries']
            if len(raw_data) == 2:
                return
            self.cursor = raw_data[-1]['content']['value']
            raw_data_lst = raw_data[:-2]
        else:
            raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions']
            self.cursor = raw_data[-1]['entry']['content']['value']
            if 'entries' in raw_data[0]:
                raw_data_lst = raw_data[0]['entries']
            else:
                return
            
        for tweet in raw_data_lst:
            if 'promoted' in tweet['entryId']:
                continue
            tweet = tweet['content']['itemContent']['tweet_results']['result']
            try:
                display_name = tweet['core']['user_results']['result']['legacy']['name']
                screen_name = '@' + tweet['core']['user_results']['result']['legacy']['screen_name']
            except Exception:   #低概率事件
                continue
            try:
                time_stamp = int(tweet['edit_control']['editable_until_msecs']) - 3600000
            except Exception as e:
                if 'edit_control_initial' in tweet['edit_control']:
                    time_stamp = int(tweet['edit_control']['edit_control_initial']['editable_until_msecs']) - 3600000
                else:
                    continue
            try:
                Favorite_Count = tweet['legacy']['favorite_count']
                Retweet_Count = tweet['legacy']['retweet_count']
                Reply_Count = tweet['legacy']['reply_count']
                _status_id = tweet['legacy']['conversation_id_str']
                tweet_url = f'https://twitter.com/{screen_name}/status/{_status_id}'
                tweet_content = tweet['legacy']['full_text'].split('https://t.co/')[0]
            except Exception as e:
                print(e)
                continue
            try:
                raw_media_lst = tweet['legacy']['extended_entities']['media']
                for _media in raw_media_lst:
                    if 'video_info' in _media:
                        media_url = get_heighest_video_quality(_media['video_info']['variants'])
                        media_type = 'Video'
                        is_image = False
                        _file_name = f'{self.folder_path}{stamp2time(time_stamp)}_{screen_name}_{hash_save_token(media_url)}.mp4'
                    else:
                        media_url = _media['media_url_https']
                        media_type = 'Image'
                        is_image = True
                        _file_name = f'{self.folder_path}{stamp2time(time_stamp)}_{screen_name}_{hash_save_token(media_url)}.png'
                    media_csv_info = [time_stamp, display_name, screen_name, tweet_url, media_type, media_url, _file_name, tweet_content, Favorite_Count, Retweet_Count, Reply_Count]
                    media_lst.append([media_url, media_csv_info, is_image])

            except KeyError:
                # 仍存在部分纯文本推文无法排除
                pass
            except Exception as e:
                print(e)

        return media_lst
    
    def search_save_text(self, url):
        #接收某页链接，保存所有文本内容

        response = httpx.get(url, headers=self._headers).text
        raw_data = json.loads(response)
        if not self.cursor: #第一次
            raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions'][-1]['entries']
            if len(raw_data) == 2:
                return  False
            self.cursor = raw_data[-1]['content']['value']
            raw_data_lst = raw_data[:-2]
        else:
            raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions']
            self.cursor = raw_data[-1]['entry']['content']['value']
            if len(raw_data) == 2:
                return  False
            raw_data_lst = raw_data[0]['entries']
            
        for tweet in raw_data_lst:
            if 'promoted' in tweet['entryId']:
                continue
            tweet = tweet['content']['itemContent']['tweet_results']['result']
            if 'tweet' in tweet and 'edit_control' in tweet['tweet']:
                tweet = tweet['tweet']
            try:
                time_stamp = int(tweet['edit_control']['editable_until_msecs']) - 3600000
            except Exception:
                if 'edit_control_initial' in tweet['edit_control']:
                    time_stamp = int(tweet['edit_control']['edit_control_initial']['editable_until_msecs']) - 3600000
                else:
                    continue
            try:
                display_name = tweet['core']['user_results']['result']['legacy']['name']
                screen_name = '@' + tweet['core']['user_results']['result']['legacy']['screen_name']
            except Exception:   #低概率事件
                continue
            
            try:
                Favorite_Count = tweet['legacy']['favorite_count']
                Retweet_Count = tweet['legacy']['retweet_count']
                Reply_Count = tweet['legacy']['reply_count']
                _status_id = tweet['legacy']['conversation_id_str']
                tweet_url = f'https://twitter.com/{screen_name}/status/{_status_id}'
                tweet_content = tweet['legacy']['full_text'].split('https://t.co/')[0]
            except Exception as e:
                print(e)
                continue

            self.csv.data_input([time_stamp, display_name, screen_name, tweet_url, tweet_content, Favorite_Count, Retweet_Count, Reply_Count])
        return True


if __name__ == '__main__':
    print('无过程输出...(๑´ڡ`๑)')
    tag_down()
    print('已完成')