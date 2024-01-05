import json
import random
import os
import time
from collections import defaultdict

import pendulum
import requests

from github_poster.loader.base_loader import BaseLoader, LoadError
from github_poster.loader.config import BILIBILI_HISTORY_URL
from github_poster.backoff import exp_backoff_with_jitter

RETRY_BASE_SEC = 2
RETRY_CAP_SEC = 30

class BilibiliLoader(BaseLoader):
    track_color = "#FB7299"
    unit = "videos"

    def __init__(self, from_year, to_year, _type, **kwargs):
        super().__init__(from_year, to_year, _type)
        self.number_by_date_dict = defaultdict(int)
        self.session = requests.Session()
        self.bilibili_cookie = kwargs.get("bilibili_cookie", "")
        self.bilibili_file = kwargs.get("bilibili_history_file")
        self._parse_bilibili_history()

    @classmethod
    def add_loader_arguments(cls, parser, optional):
        parser.add_argument(
            "--bilibili_cookie",
            dest="bilibili_cookie",
            type=str,
            required=optional,
            help="The cookie for the bilibili website(XHR)",
        )
        parser.add_argument(
            "--bilibili_history_file",
            dest="bilibili_history_file",
            type=str,
            default=os.path.join("IN_FOLDER", "bilibili-history.json"),
            help="bilibili history file path",
        )

    def _parse_bilibili_history(self):
        if os.path.exists(self.bilibili_file):
            with open(self.bilibili_file, "r") as f:
                self.number_by_date_dict = json.load(f)

    def _writeback_bilibili_history(self):
        with open(self.bilibili_file, "w") as f:
            json.dump(self.number_by_date_dict, f, sort_keys=True)

    def get_api_data(self, max_oid="", view_at="", data_list=[], total_retry=0):
        if total_retry > 120:
            raise LoadError("Maximum retry amount reached")

        try:
            r = self.session.get(BILIBILI_HISTORY_URL.format(max_oid=max_oid, view_at=view_at))
        except requests.exceptions.ConnectionError as e:
            print(e)
            wait_sec = exp_backoff_with_jitter(RETRY_BASE_SEC, RETRY_CAP_SEC, total_retry)
            print(f"Retrying ... in {wait_sec}")
            time.sleep(wait_sec)
            return self.get_api_data(max_oid=max_oid, view_at=view_at, data_list=data_list, total_retry=total_retry + 1)

        if not r.ok:
            try:
                errorMsg = r.json()
            except requests.exceptions.JSONDecodeError:
                raise LoadError("Can not get bilibili history data, please check your cookie")

            if errorMsg["code"] == -412 and errorMsg["message"]:
                wait_sec = exp_backoff_with_jitter(RETRY_BASE_SEC, RETRY_CAP_SEC, total_retry)
                print(f"Request was banned, retrying ... in {wait_sec}")
                time.sleep(wait_sec)
                return self.get_api_data(max_oid=max_oid, view_at=view_at, data_list=data_list, total_retry=total_retry + 1)
            else:
                raise LoadError("Can not get bilibili history data, please check your cookie")

        data = r.json()["data"]
        if not data["list"]:
            return data_list
        lst = data["list"]
        max_oid = lst[-1]["history"]["oid"]
        view_at = lst[-1]["view_at"]
        data_list.extend(lst)
        print(len(data_list))
        # spider rule
        time.sleep(.2 + 1 * random.random())
        return self.get_api_data(max_oid=max_oid, view_at=view_at, data_list=data_list)

    def make_track_dict(self):
        data_list = self.get_api_data()
        new_watch_dict = defaultdict(int)
        for d in data_list:
            date_str = pendulum.from_timestamp(
                d["view_at"], tz=self.time_zone
            ).to_date_string()
            new_watch_dict[date_str] += 1
        for i in new_watch_dict:
            if (
                i not in self.number_by_date_dict
                or new_watch_dict[i] > self.number_by_date_dict[i]
            ):
                self.number_by_date_dict[i] = new_watch_dict[i]
        self._writeback_bilibili_history()
        for _, v in self.number_by_date_dict.items():
            self.number_list.append(v)

    def get_all_track_data(self):
        # first we need to activate the session with cookie str from `chrome`
        self.session.cookies = self.parse_cookie_string(self.bilibili_cookie)
        self.session.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': "macOS",
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }

        self.make_track_dict()
        self.make_special_number()
        return self.number_by_date_dict, self.year_list
