# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "certifi==2025.6.15",
#     "requests==2.32.4",
#     "ruff==0.12.0",
# ]
# ///

from certifi import where
from dataclasses import asdict, dataclass, field
from json import dumps
import requests
from os import environ
from pathlib import Path
from typing import Dict, List

GITHUB_API_ENDPOINT = "https://api.github.com/graphql"
GITHUB_TOKEN = environ.get("GH_TOKEN", "ENOTOKEN")
DATA_DIR = "data"


@dataclass
class Repository:
    owner: str
    name: str


@dataclass
class Reply:
    id: str
    url: str
    body: str
    author: str
    created_at: str

    def as_dict(self):
        return asdict(self)


@dataclass
class Comment:
    id: str
    url: str
    body: str
    author: str
    created_at: str
    replies: List[Reply] = field(default_factory=list)

    def as_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "body": self.body,
            "author": self.author,
            "created_at": self.created_at,
            "replies": [reply.as_dict() for reply in self.replies],
        }


@dataclass
class Discussion:
    id: str
    number: int
    title: str
    body: str
    author: str
    created_at: str
    url: str
    comments: List[Comment] = field(default_factory=list)

    def as_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "body": self.body,
            "author": self.author,
            "created_at": self.created_at,
            "comments": [comment.as_dict() for comment in self.comments],
        }


def query(session: requests.Session, payload) -> Dict[str, any]:
    try:
        response = session.post(GITHUB_API_ENDPOINT, json={**payload}, verify=where())

        if response.status_code >= 400:
            raise RuntimeError(f"status code {response.status_code} from {payload}")

        raw_data = response.json()
        raise_response_errors(raw_data)

        return raw_data.get("data", {})

    except Exception as e:
        print(f"query {payload} failed")


def raise_response_errors(data: Dict[str, any]) -> None:
    if "errors" in data:
        raise RuntimeError(
            f"Query returned successfully, but query itself invalid {data['errors']}"
        )
    return


def check_more_pages(data: Dict[str, any]) -> bool:
    return data.get("hasNextPage", False)


def get_discussions(session: requests.Session, repo: Repository) -> List[Discussion]:
    discussions: List[Discussion] = []
    graphql_query = """
    query Q($owner: String!, $repo: String!, $cursor: String) {
        repository(owner: $owner, name: $repo) {
            discussions(first: 32, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    number
                    body
                    title
                    author {
                        login
                    }
                    createdAt
                    url
                }
            }
        }
    }
    """
    variables = {"owner": repo.owner, "repo": repo.name, "cursor": None}
    while True:
        data = query(session, payload={"query": graphql_query, "variables": variables})
        nodes = data.get("repository", {}).get("discussions", {}).get("nodes")
        page_info = data.get("repository", {}).get("discussions", {}).get("pageInfo")
        has_more_pages = check_more_pages(page_info)
        discussions.extend(
            [
                Discussion(
                    n.get("id"),
                    n.get("number"),
                    n.get("title"),
                    n.get("body"),
                    n.get("author", {}).get("login", "ENOAUTHOR"),
                    n.get("createdAt"),
                    n.get("url"),
                )
                for n in nodes
            ]
        )
        if not has_more_pages:
            break
        variables["cursor"] = page_info["endCursor"]
    return discussions


def get_discussion_comments(session: requests.Session, discussion: Discussion) -> List[Comment]:
    comments = []
    graphql_query = """
    query Q($discussionId: ID!, $cursor: String) {
      node(id: $discussionId) {
        ... on Discussion {
          comments(first: 32, after: $cursor) {
            totalCount
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              body
              url
              createdAt
              author {
                login
              }              
              replies(first: 96, after: $cursor) {
                totalCount
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  body
                  author {
                    login
                  }
                  createdAt
                  url
                }
              }
            }
          }
        }
      }
    }
    """
    variables = {"discussionId": discussion.id, "cursor": None}
    while True:
        data = query(session, payload={"query": graphql_query, "variables": variables})
        nodes = data.get("node", {}).get("comments", {}).get("nodes")
        page_info = data.get("node", {}).get("comments", {}).get("pageInfo")
        has_more_pages = check_more_pages(page_info)
        comments.extend(
            [
                Comment(
                    n.get("id"),
                    n.get("url"),
                    n.get("body"),
                    n.get("author", {}).get("login"),
                    n.get("createdAt"),
                    replies=[
                        Reply(
                            reply.get("id"),
                            reply.get("url"),
                            reply.get("body"),
                            reply.get("author", {}).get("login"),
                            reply.get("createdAt"),
                        )
                        for reply in n.get("replies", {}).get("nodes")
                    ],
                )
                for n in nodes
            ]
        )
        if not has_more_pages:
            break
        variables["cursor"] = page_info["endCursor"]
    return comments


def export_discussion(
    session: requests.Session, repository: Repository, discussion: Discussion
) -> str:
    """
    Export a GitHub discussion serialized as a Markdown buffer to save to
    disk.
    """
    data = f"# Metadata\r\n\r\n"
    data += f"title:{discussion.title}\r\n\r\n"
    data += f"author: [github.com/{discussion.author}](https://github.com/{discussion.author})\r\n\r\n"
    data += f"url: [{discussion.url}]({discussion.url})\r\n\r\n"
    data += f"created: {discussion.created_at}\r\n\r\n"
    data += f"id: {discussion.id}\r\n\r\n"
    data += "\r\n\r\n"
    data += f"# Post\r\n\r\n"
    data += discussion.body
    data += "\r\n\r\n"
    data += f"# Comments\r\n"
    data += "\r\n\r\n"

    for idx, comment in enumerate(discussion.comments):
        data += "\r\n\r\n"
        data += f"## Comment {idx + 1}\r\n\r\n"
        data += f"author: [github.com/{comment.author}](https://github.com/{comment.author})\r\n\r\n"
        data += f"url: [{comment.url}]({comment.url})\r\n\r\n"
        data += f"created: {comment.created_at}\r\n\r\n"
        data += f"id: {comment.id}\r\n\r\n"
        data += comment.body
        data += "\r\n\r\n"
        data += "### Replies\r\n\r\n"
        for idx, reply in enumerate(comment.replies):
            data += "\r\n\r\n"
            data += f"#### Reply {idx + 1}\r\n\r\n"
            data += f"author: [github.com/{reply.author}](https://github.com/{reply.author})\r\n\r\n"
            data += f"url: [{reply.url}]({reply.url})\r\n\r\n"
            data += f"created: {reply.created_at}\r\n\r\n"
            data += f"id: {reply.id}\r\n\r\n"
            data += reply.body
            data += "\r\n\r\n"

    return data


def main() -> None:
    """
    This function is a handler for all processing when the script is invoked
    from the command line.
    """
    session: requests.Session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }
    )
    owner = "fedramp"
    repositories = [
        Repository(owner, name="community"),
        Repository(owner, name="applying-existing-frameworks-cwg"),
        Repository(owner, name="automating-assessment-cwg"),
        Repository(owner, name="continuous-reporting-cwg"),
        Repository(owner, name="rev5-continuous-monitoring-cwg"),
    ]
    data_files = Path(DATA_DIR)
    data_files.mkdir(parents=True, exist_ok=True)
    for repo in repositories:
        repo_files = Path(f"{data_files}/{repo.owner}/{repo.name}/discussions")
        repo_files.mkdir(parents=True, exist_ok=True)
        discussions = get_discussions(session, repo)
        print(
            f"retrieved from {repo.owner}/{repo.name} {len(discussions)} discussion(s)"
        )
        for discussion in discussions:
            discussion.comments = get_discussion_comments(session, discussion)
            discussion_file_markdown = f"{repo_files}/{discussion.number}.md"
            discussion_file_json = f"{repo_files}/{discussion.number}.json"
            print(f"saving export of {discussion.url} to {discussion_file_markdown}")
            with (
                open(discussion_file_markdown, "w") as markdown_fd,
                open(discussion_file_json, "w") as json_fd,
            ):
                markdown_fd.write(export_discussion(session, repo, discussion))
                print(f"saved Markdown export of {discussion.url} to {discussion_file_markdown}")
                json_fd.write(dumps(discussion.as_dict(), indent=2))
                print(f"saved JSON export of {discussion.url} to {discussion_file_json}")


if __name__ == "__main__":
    main()
