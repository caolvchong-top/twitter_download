import httpx

import os
import re
import json
import csv
import time
from datetime import datetime

from user_info import User_info
from url_utils import quote_url



##########配置区域##########
cookie = 'auth_token=xxxxxxxxxxx; ct0=xxxxxxxxxxx;'
# 填入 cookie (auth_token与ct0字段) //重要:替换掉其中的x即可, 注意不要删掉分号

user_lst = ['jeleechandayo','yorukura_anime']
# 填入要下载的用户名(@后面的字符),支持多用户下载,在列表里添加即可

time_range = "2024-04-21:2030-01-01"
# 时间范围限制,格式如 1990-01-01:2030-01-01

has_retweet = False
# 是否包含转推

##########配置区域##########



def time2stamp(timestr:str) -> int:
    datetime_obj = datetime.strptime(timestr, "%Y-%m-%d")
    msecs_stamp = int(time.mktime(datetime_obj.timetuple()) * 1000.0 + datetime_obj.microsecond / 1000.0)
    return msecs_stamp

start_time,end_time = time_range.split(':')
start_time_stamp,end_time_stamp = time2stamp(start_time),time2stamp(end_time)

class csv_gen():
    def __init__(self, save_path:str, user_name, screen_name, tweet_range) -> None:
        self.f = open(f'{save_path}/{screen_name}-{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}-text.csv', 'w', encoding='utf-8-sig', newline='')
        self.writer = csv.writer(self.f)

        #初始化
        self.writer.writerow([user_name, '@' + screen_name])
        self.writer.writerow(['Tweet Range : ' + tweet_range])
        self.writer.writerow(['Save Path : ' + save_path])
        main_par = ['Display Name', 'User Name', 'Tweet Date', 'Tweet URL', 'Tweet Content', 'Favorite Count', 
                    'Retweet Count', 'Reply Count']
        self.writer.writerow(main_par)

        pass

    def csv_close(self):
        self.f.close()

    def stamp2time(self, msecs_stamp:int) -> str:
        timeArray = time.localtime(msecs_stamp/1000)
        otherStyleTime = time.strftime("%Y-%m-%d %H:%M", timeArray)
        return otherStyleTime
    
    def data_input(self, main_par_info:list) -> None:   #数据格式参见 main_par
        main_par_info[2] = self.stamp2time(main_par_info[2])    #传进来的是 int 时间戳, 故转换一下
        self.writer.writerow(main_par_info)


def time_comparison(now):
    start_label = True
    start_down  = False
    #twitter : latest -> old
    if now >= start_time_stamp and now <= end_time_stamp:     #符合时间条件，下载
        start_down = True
    elif now < start_time_stamp:     #超出时间范围，结束
        start_label = False
    return [start_down, start_label]


def get_other_info(_user_info, _headers):
    url = 'https://twitter.com/i/api/graphql/xc8f1g7BYqr6VTzTbvNlGw/UserByScreenName?variables={"screen_name":"' + _user_info.screen_name + '","withSafetyModeUserFields":false}&features={"hidden_profile_likes_enabled":false,"hidden_profile_subscriptions_enabled":false,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"subscriptions_verification_info_verified_since_enabled":true,"highlights_tweets_tab_ui_enabled":true,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}&fieldToggles={"withAuxiliaryUserLabels":false}'
    try:
        response = httpx.get(quote_url(url), headers=_headers).text
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



class text_down():
    def __init__(self, screen_name):
        self._user_info = User_info(screen_name)

        self._headers = {
            'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        }
        self._headers['cookie'] = cookie
        re_token = 'ct0=(.*?);'
        self._headers['x-csrf-token'] = re.findall(re_token, cookie)[0]

        if not get_other_info(self._user_info, self._headers):
            return False
        print_info(self._user_info)

        self._headers['referer'] = 'https://twitter.com/' + self._user_info.screen_name

        self.folder_path = os.getcwd() + os.sep + screen_name + os.sep

        if not os.path.exists(self.folder_path):   #创建文件夹
            os.makedirs(self.folder_path)

        self.csv_file = csv_gen(self.folder_path, self._user_info.name, self._user_info.screen_name, time_range)

        self.cursor = ''

        self.get_clean_save()

        self.csv_file.csv_close()

        pass

    def get_clean_save(self):
        while True:
            ###get_all_data###
            url = 'https://twitter.com/i/api/graphql/9zyyd1hebl7oNWIPdA8HRw/UserTweets?variables={"userId":"' + self._user_info.rest_id + '","count":20,"cursor":"' + self.cursor + '","includePromotedContent":true,"withQuickPromoteEligibilityTweetFields":true,"withVoice":true,"withV2Timeline":true}&features={"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"articles_preview_enabled":true,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"tweet_with_visibility_results_prefer_gql_media_interstitial_enabled":true,"rweb_video_timestamps_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_enhance_cards_enabled":false}&fieldToggles={"withArticlePlainText":false}'

            response = httpx.get(quote_url(url), headers=self._headers).text
            try:
                raw_data = json.loads(response)
            except Exception:
                if 'Rate limit exceeded' in response:
                    print('API次数已超限')
                else:
                    print('获取数据失败')
                print(response)
                return
            raw_tweet_lst = raw_data['data']['user']['result']['timeline_v2']['timeline']['instructions'][-1]['entries']
            if len(raw_tweet_lst) == 2:
                return
            if self.cursor == raw_tweet_lst[-1]['content']['value']:
                return
            self.cursor = raw_tweet_lst[-1]['content']['value']

            for tweet in raw_tweet_lst:
                if 'promoted-tweet' in tweet['entryId']:        #排除广告
                        continue
                if 'tweet' in tweet['entryId']:
                    raw_text = tweet['content']['itemContent']['tweet_results']['result']
                    if 'tweet' in raw_text:
                        raw_text = raw_text['tweet']
                    try:
                        _time_stamp = int(raw_text['edit_control']['editable_until_msecs']) - 3600000
                    except Exception:
                        if 'edit_control_initial' in raw_text['edit_control']:
                            _time_stamp = int(raw_text['edit_control']['edit_control_initial']['editable_until_msecs']) - 3600000
                        else:
                            continue
                    if 'retweeted_status_result' in raw_text['legacy']:       #转推判断
                        if has_retweet:
                            raw_text = raw_text['legacy']['retweeted_status_result']['result']
                            if 'tweet' in raw_text:
                                raw_text = raw_text['tweet']
                            _display_name = raw_text['core']['user_results']['result']['legacy']['name']
                            _screen_name = '@' + raw_text['core']['user_results']['result']['legacy']['screen_name']
                        else:
                            continue
                    else:
                        _display_name = ''
                        _screen_name = ''

                    _results = time_comparison(_time_stamp)
                    if not _results[1]:     #超出时间范围，结束
                        return
                    if not _results[0]:     #不符合时间条件，跳过
                        continue
                    
                    _Favorite_Count = raw_text['legacy']['favorite_count']
                    _Retweet_Count = raw_text['legacy']['retweet_count']
                    _Reply_Count = raw_text['legacy']['reply_count']
                    _status_id = raw_text['legacy']['conversation_id_str']
                    screen_name = raw_text['core']['user_results']['result']['legacy']['screen_name']
                    _tweet_url = f'https://twitter.com/{screen_name}/status/{_status_id}'
                    if 'note_tweet' in raw_text:
                        _tweet_content = raw_text['note_tweet']['note_tweet_results']['result']['text'].split('https://t.co/')[0]
                    else:
                        _tweet_content = raw_text['legacy']['full_text'].split('https://t.co/')[0]

                    self.csv_file.data_input([_display_name, _screen_name, _time_stamp, _tweet_url, _tweet_content, _Favorite_Count, _Retweet_Count, _Reply_Count])

if __name__ == '__main__':
    for user in user_lst:
        text_down(user)
    print('完成 (๑´ڡ`๑)')