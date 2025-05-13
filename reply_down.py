import httpx

import asyncio
import re
import os
import csv
import time
import json
from datetime import datetime
from urllib.parse import quote
from url_utils import quote_url
from tag_down import get_heighest_video_quality
from tag_down import hash_save_token
from tag_down import stamp2time
from transaction_generate import get_transaction_id
from transaction_generate import get_url_path

##########配置区域##########

cookie = 'auth_token=xxxxxxxxxxx; ct0=xxxxxxxxxxx;'
# 填入 cookie (auth_token与ct0字段) //重要:替换掉其中的x即可, 注意不要删掉分号

target_user = [
    'https://x.com/matchach/status/1855589540905590962',
    '@lilmonix3',
    'https://x.com/yorukura_anime/status/1895307947950924182'
]
# 填入目标用户或指定推文链接, 支持混合与批量, 如上述例子.
# 当目标为单个推文时, 在根目录下生成以推文ID为名的文件夹.
# 当目标为用户时, 在根目录下生成用户名文件夹.

# csv文件命名格式: ./{Tweet_ID or User_Name}/{datetime.now}-Reply.csv
# 媒体文件命名格式: ./{Tweet_ID or User_Name}/{reply_date}_{replier_user_name}_{md5(media_url)[:4]}_reply.{mp4/png}


time_range = "2024-02-06:2024-08-06"
# 限定时间范围, 指定用户时生效, 格式如2023-02-01:2024-05-06, 不填留空则默认无限制.

media_down = True
# 开启后将同时下载评论内容中的媒体文件.

# ------------------------ #

def del_special_char(string):
    string = re.sub(r'[^#\u4e00-\u9fa5\u0030-\u0039\u0041-\u005a\u0061-\u007a\u3040-\u31FF\.]', '', string)
    return string

class csv_gen():
    def __init__(self, save_path:str) -> None:
        self.f = open(f'{save_path}{datetime.now().strftime("%Y-%m-%d %H-%M-%S")}-Reply.csv', 'w', encoding='utf-8-sig', newline='')
        self.writer = csv.writer(self.f)

        #初始化
        self.writer.writerow(['Run Time : ' + datetime.now().strftime('%Y-%m-%d %H-%M-%S')])

        main_par = ['Parent Tweet URL', 'Replier Display Name', 'Replier User Name', 'Reply Date', 'Reply Content', 'Reply URL', 
                    'Reply Favorite Count', 'Reply Retweet Count', 'Reply Reply Count']

        self.writer.writerow(main_par)

    def csv_close(self):
        self.f.close()

    def stamp2time(self, msecs_stamp:int) -> str:
        timeArray = time.localtime(msecs_stamp/1000)
        otherStyleTime = time.strftime("%Y-%m-%d %H:%M", timeArray)
        return otherStyleTime
    
    def data_input(self, main_par_info:list) -> None:   #数据格式参见 main_par
        main_par_info[3] = self.stamp2time(main_par_info[3])    #传进来的是 int 时间戳, 故转换一下
        self.writer.writerow(main_par_info)

def download_control(media_lst):
    async def _main():
        async def down_save(url, _file_name, is_image):
            if is_image:
                url += '?format=png&name=4096x4096'

            count = 0
            while True:  #下载失败重试次数
                try:
                    async with semaphore:
                        async with httpx.AsyncClient() as client:
                            response = await client.get(quote_url(url), timeout=(3.05, 16))        #如果出现第五次或以上的下载失败,且确认不是网络问题,可以适当降低最大并发数量
                    with open(_file_name,'wb') as f:
                        f.write(response.content)
                    break
                except Exception as e:
                    if count >= 50:
                        print(f'{url}=====>第{count}次下载失败,已跳过')
                        break
                    count += 1
                    print(e)
                    print(f'{url}=====>第{count}次下载失败,正在重试')

        semaphore = asyncio.Semaphore(max_concurrent_requests)
        await asyncio.gather(*[asyncio.create_task(down_save(url[0], url[1], url[2])) for url in media_lst])   # 0:url 1:_file_name 2:is_image

    asyncio.run(_main())


##########高级配置区域##########
# 如无特殊需要 请勿修改

max_concurrent_requests = 8
# 最大并发数量, 默认为8, 对网络有自信的可以调高; 遇到多次下载失败时适当降低.

min_replies = 1
# 筛选最小回复数, 只获取大于该数值的推文的评论区.

min_faves = 0
# 筛选最小喜欢数, 同上.

min_retweets = 0
# 筛选最小转推数, 同上.

search_advanced = ''
# 即tag_down中的高级搜索
# 当填写此项时, 所有配置都将失效, 包括target_user, 下载的内容以该组合获取到的内容为准.
# 使用时建议在组合中限定时间范围, 以防API调用次数超限.
# 自定义组装地址: https://x.com/search-advanced

# ------------------------ #


class Reply_down():
    def __init__(self, _target):
        self.target = _target
        self.folder_path = os.getcwd() + os.sep

        self._headers = {
            'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        }
        self._headers['cookie'] = cookie
        re_token = 'ct0=(.*?);'
        self._headers['x-csrf-token'] = re.findall(re_token, cookie)[0]

        self.cursor = ''

        self.ct = get_transaction_id()

        if self.get_querystring():  #指定用户
            self.folder_path = os.getcwd() + os.sep + del_special_char(self.user_name) + os.sep
            if not os.path.exists(self.folder_path):   #创建文件夹
                os.makedirs(self.folder_path)
            self.csv = csv_gen(self.folder_path)
            self.get_result()

        else:   #指定推文
            self.folder_path = os.getcwd() + os.sep + del_special_char(self.tweet_id) + os.sep
            if not os.path.exists(self.folder_path):   #创建文件夹
                os.makedirs(self.folder_path)
            self.csv = csv_gen(self.folder_path)
            self.id2reply(self.tweet_id)

        self.csv.csv_close()

    def id2reply(self, tweet_id:str):
        _cursor = ''
        media_lst = []
        is_completed = False
        while not is_completed:
            url = 'https://x.com/i/api/graphql/_8aYOgEDz35BrBcBal1-_w/TweetDetail?variables={"focalTweetId":"' + tweet_id + '","cursor":"' + _cursor + '","referrer":"tweet","with_rux_injections":false,"rankingMode":"Recency","includePromotedContent":false,"withCommunity":true,"withQuickPromoteEligibilityTweetFields":true,"withBirdwatchNotes":true,"withVoice":true}&features={"rweb_video_screen_enabled":false,"profile_label_improvements_pcf_label_in_post_enabled":true,"rweb_tipjar_consumption_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":true,"responsive_web_jetfuel_frame":false,"responsive_web_grok_share_attachment_enabled":true,"articles_preview_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"responsive_web_grok_show_grok_translated_post":false,"responsive_web_grok_analysis_button_from_backend":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_enhance_cards_enabled":false}&fieldToggles={"withArticleRichContentState":true,"withArticlePlainText":false,"withGrokAnalyze":false,"withDisallowedReplyControls":false}'
            _path = get_url_path(url)
            url = quote_url(url)
            self._headers['x-client-transaction-id'] = self.ct.generate_transaction_id(method='GET', path=_path)
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
            
            raw_data = raw_data['data']['threaded_conversation_with_injections_v2']['instructions'][0]['entries']
            if not _cursor: #第一页第一条默认为父推文
                if len(raw_data) == 1:
                    return
                raw_data.pop(0)

            if 'cursor-' not in raw_data[-1]['entryId']:
                is_completed = True
            else:
                _cursor = raw_data[-1]['content']['itemContent']['value']

            for _reply in raw_data:
                try:
                    if 'conversationthread' in _reply['entryId']:
                        _reply = _reply['content']['items'][0]
                        if 'conversationthread' not in _reply['entryId']:
                            continue
                        _reply = _reply['item']['itemContent']['tweet_results']['result']
                        
                        if 'editable_until_msecs' in _reply['edit_control']:
                            time_stamp = int(_reply['edit_control']['editable_until_msecs']) - 3600000
                        elif 'edit_control_initial' in _reply['edit_control'] and 'editable_until_msecs' in _reply['edit_control']['edit_control_initial']:
                            time_stamp = int(_reply['edit_control']['edit_control_initial']['editable_until_msecs']) - 3600000
                        else:
                            continue

                        parent_tweet_url = f'https://x.com/{self.user_name}/status/{tweet_id}'
                        replier_display_name = _reply['core']['user_results']['result']['legacy']['name']
                        replier_user_name = '@' + _reply['core']['user_results']['result']['legacy']['screen_name']
                        reply_date = time_stamp
                        reply_content = _reply['legacy']['full_text']
                        reply_url = f'https://x.com/{replier_user_name}/status/{_reply["legacy"]["id_str"]}'
                        reply_favorite_count = _reply['legacy']['favorite_count']
                        reply_retweet_count = _reply['legacy']['retweet_count']
                        reply_reply_count = _reply['legacy']['reply_count']
                    else:
                        continue
                except Exception as e:
                    print(e)
                    continue

                if media_down and 'extended_entities' in _reply['legacy']:
                    try:
                        raw_media_lst = _reply['legacy']['extended_entities']['media']
                        for _media in raw_media_lst:
                            if 'video_info' in _media:
                                media_url = get_heighest_video_quality(_media['video_info']['variants'])
                                is_image = False
                                _file_name = f'{self.folder_path}{stamp2time(time_stamp)}_{replier_user_name}_{hash_save_token(media_url)}_reply.mp4'
                            else:
                                media_url = _media['media_url_https']
                                is_image = True
                                _file_name = f'{self.folder_path}{stamp2time(time_stamp)}_{replier_user_name}_{hash_save_token(media_url)}_reply.png'

                            media_lst.append([media_url, _file_name, is_image])
                    except Exception as e:
                        print(e)

                _csv_info = [parent_tweet_url, replier_display_name, replier_user_name, reply_date, reply_content, reply_url, reply_favorite_count, reply_retweet_count, reply_reply_count]
                self.csv.data_input(_csv_info)

                if media_lst:
                    download_control(media_lst)
                    


    def get_querystring(self):
        if search_advanced:
            self.querystring = search_advanced
        else:
            if '/status/' in self.target: #指定推文
                self.tweet_id = self.target.split('/status/')[-1]
                self.user_name = self.target.split('/')[3]
                return False
            else:   #指定用户
                self.user_name = self.target.split('@')[-1]
                if time_range:
                    self.since_time, self.until_time = time_range.split(':')
                    self.querystring = f"(from:{self.user_name}) min_replies:{min_replies} min_faves:{min_faves} min_retweets:{min_retweets} until:{self.until_time} since:{self.since_time}"
                else:
                    self.querystring = f"(from:{self.user_name}) min_replies:{min_replies} min_faves:{min_faves} min_retweets:{min_retweets}"
            return True

    def get_result(self):
        _headers = self._headers
        _headers['referer'] = f'https://twitter.com/search?q={quote(self.querystring)}&src=typed_query&f=media'

        def get_tweet_list(url, _headers):
            tweet_lst = []

            _path = get_url_path(url)
            url = quote_url(url)
            self._headers['x-client-transaction-id'] = self.ct.generate_transaction_id(method='GET', path=_path)
            response = httpx.get(url, headers=_headers).text
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
                raw_data_lst = raw_data[:-2]
            else:
                raw_data = raw_data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions']
                self.cursor = raw_data[-1]['entry']['content']['value']
                if 'entries' in raw_data[0]:
                    raw_data_lst = raw_data[0]['entries']
                else:
                    return
                
            for tweet in raw_data_lst:
                if 'tweet-' in tweet['entryId']:
                    tweet_id = tweet['entryId'].split('tweet-')[-1]
                    tweet_lst.append(tweet_id)
            return tweet_lst
                
        while True:
            url = 'https://x.com/i/api/graphql/yiE17ccAAu3qwM34bPYZkQ/SearchTimeline?variables={"rawQuery":"' + quote(self.querystring) + '","count":"20","cursor":"' + self.cursor + '","querySource":"typed_query","product":"Latest"}&features={"rweb_video_screen_enabled":false,"profile_label_improvements_pcf_label_in_post_enabled":true,"rweb_tipjar_consumption_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":true,"responsive_web_jetfuel_frame":false,"responsive_web_grok_share_attachment_enabled":true,"articles_preview_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"responsive_web_grok_show_grok_translated_post":false,"responsive_web_grok_analysis_button_from_backend":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_enhance_cards_enabled":false}'
            url = quote_url(url)
            tweet_lst = get_tweet_list(url, _headers)
            if not tweet_lst:
                break
            for tweet_id in tweet_lst:
                self.id2reply(tweet_id)

for _target in target_user:
    print(f'开始处理: {_target}')
    Reply_down(_target)
    print(f'处理完成: {_target}')
