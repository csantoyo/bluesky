import requests
import json
import functools
from datetime import datetime, timezone

class Resource:
    def __init__(self, resource_json):
        self.resource_json = resource_json

        for key, value in resource_json.items():
            if not isinstance(value, dict) and not isinstance(value, list):
                setattr(self,key,value)
            elif isinstance(value, dict):
                setattr(self,key, Resource(value))
            elif isinstance(value, list):
                value_list = []
                if len(value) > 0:
                    for entry in value:
                        if isinstance(entry, dict):
                            value_list.append(Resource(entry))
                        else:
                            value_list.append(entry)

                    setattr(self, key, value_list)
                else:
                    setattr(self, key, value_list)
            
    def __str__(self):
        return str(self.resource_json)
    

class Feed:
    def __init__(self, feed):
        self.posts = list()
        for entry in feed:
            self.posts.append(Post(entry['post']))

class Post(Resource):
    def __init__(self, post):
        super().__init__(post)

class Profile(Resource):
    def __init__(self, profile):
        super().__init__(profile)

class Session(Resource):
    def __init__(self, session):
        super().__init__(session)

def client_verifier(func):
    @functools.wraps(func)
    def check_client_instance(self, *args, **kwargs):
        if not self.is_authenticated:
            raise ValueError("Client is not authenticated")
        return func(self, *args, **kwargs)
    return check_client_instance


class BlueSkyClient:
    def __init__(self, identifier=None, password=None):
        self.identifier = identifier
        self.password = password
        self.is_authenticated = False
        self.pds_url = "https://bsky.social"
        
        if self.identifier is not None and self.password is not None:
            resp = requests.post(
                "https://bsky.social" + "/xrpc/com.atproto.server.createSession",
                json={"identifier": identifier, "password": password},
            )
            resp.raise_for_status()
            profile_resp = json.loads(resp.text)

            self.session = Session(profile_resp)
            self.is_authenticated = True
            
    @staticmethod
    def get_user_feed(profile_handle):
        api_endpoint = "/xrpc/app.bsky.feed.getAuthorFeed"
        url = f"https://public.api.bsky.app{api_endpoint}?actor={profile_handle}"
        resp = requests.get(url)

        # Error check response
        resp.raise_for_status()
        
        resp_json = json.loads(resp.text)

        return Feed(resp_json["feed"])

    @staticmethod
    def get_user_profile(profile_handle):
        api_endpoint = "/xrpc/app.bsky.actor.getProfile"
        url = f"https://public.api.bsky.app{api_endpoint}?actor={profile_handle}"
        resp = requests.get(url)

        # Error check response
        resp.raise_for_status()
        
        resp_json = json.loads(resp.text)
        
        return Profile(resp_json)
        
    @client_verifier
    def post(self, text: str, post_type: str = "app.bsky.feed.post", created_at: str = None,  **kwargs):
        api_endpoint = "/xrpc/com.atproto.repo.createRecord"
        
        if created_at is None:
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        post = {
            "$type": post_type,
            "text": text,
            "createdAt": now,
        }

        # Unpack keyword arguments that belong to this post.
        for key, value in kwargs.items():
            post[key] = value

        resp = requests.post(
            self.pds_url + api_endpoint,
            headers={"Authorization": "Bearer " + self.session.accessJwt},
            json={
                "repo": self.session.did,
                "collection": post_type,
                "record": post,
            },
        )

        resp.raise_for_status()

    def get_record(self, record: str):
        api_endpoint = "/xrpc/com.atproto.repo.getRecord"
        api_uri = self.pds_url + api_endpoint

        resp = requests.get(
            api_uri,
            params=record,
        )

        resp.raise_for_status()

        return Post(resp.json())

    @staticmethod
    def __create_get_record_form__(post: Post):
        record_form = {}
        
        record_form["parent"] = {"uri": post.uri, "cid": post.cid} 
        record_form["root"] = {"uri": post.uri, "cid": post.cid} 
            
        if hasattr(post, "value"):
            if hasattr(post.value, "reply"):
                record_form["root"] = {"uri": post.value.reply.root.uri, "cid": post.value.reply.root.cid} 

        return record_form
        
    @client_verifier
    def reply_to_post(self, in_post: Post, text: str):
        post_record = {}
        if not isinstance(in_post, Post):
            raise TypeError(f"{in_post} must to of type Post not {type(in_post)}")

        post_record["reply"] = BlueSkyClient.__create_get_record_form__(in_post)

        self.post(text=text, **post_record)