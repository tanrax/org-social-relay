# Org Social Relay

## Challenges and solutions

The current structure seems very idealized, there are multiple problems a working org-social relay spec will need to solve:

### Network structure

The relays need to discover each other, right? 
Other than the main org-social relay list (possibly other ones), 
relays should also provide their own "connected relays" list.
Then, relays could go from one relay to the full network with no 
The idea of "connected feeds" list seems also nice - everything is public anyways.

Also, are we allowing for a single feed to be on multiple nodes?
Properly checking for that is somewhat painfull though, 
and can fail under some circumstances,
so there would have to be some mechanism for that either way.

### Some authentication is needed
Specifically, I think there should be some token 
    (more likely a public-private key pair, signing based system),
that is associated with a feed upon registration. 
It would identify the user on that specific relay,
with an included method of checking that token by other relays. <br>
It would allow for not only registering feeds,
but also un-registering them safely
    (wouldn't want just anyone to be able to remove a feed, 
    but the urls can change over time, 
    or one could leave). <br>
Same goes for joining/leaving groups, 
they should work on a consent basis rather than just allowing someone to add you to a group.


That of course is the case only for public-facing apis, if one would be hosting their own, private relay, they could just disable all "privileged" reqests.
But public relays are needed - not everyone has the capability to host an internet-facing relay, while hosting a static site and using someone elses relay to register is very easy. 

### Identity problem (somewhat related to authentication)
The identity of a user could very easily be broken in an open environment. 
Of course, org-social works mostly on a link basis anyway,
but that't fine, since currently sources are added solely by the user, 
and are supposed to be checked for correctness by them, 
and displaying source urls along with posts mostly solve any authentication concerns<br>
But what about for when the clients move to the decentralized-federated system?<br>
I envision a possible scenario where:
- user A registers their own feed on relay 1, with url http://some.site/social.org
- user B register a feed that mimicks A@1's profile, on relay 2, with url http://some2.site/social.org
- user B joins a group #G that user C@3 is in, but A might not be
Now, user C@3 when checking #G will get posts from B@2 that for him look exactly like posts from A@1 would -
it's not like they know what A@1's real url even is.
Effectively, B has assumed the identity of A from the perspective of C

There are ways to prevent that:
a) The network should allow for adding feeds only for different usernames across the network, but then users would have to maintain a list of their feed urls as part of at most a single feed, considered main, that would have to be in the network first. This way, username conflicts could be at least detected and marked invalid - though that has the problem of not being able to choose the correct one.
b) The users would have to maintain a private/public key pair, with a "profile signature" + claimed main profile link as part of their extra feeds and a public key in the "main profile" - though after detecting conflicts there is the same problem as in a)
c) Restrict a user to a single url base, ex: http://some.tld/directory/*, where they would claim their ownership with a file in the root of that directory, and their subfeed would all be somewhere there. This also has the same problem as the last two.
d) Some combination of the above.

For solving the "duplicate" problem, there could be a certificate-based system associated with the registration process. It would be based on asking the network for a check for any impersonation (based on a scheme from above), most likely the ones declared in some centralized list. Such list, probably also signed by the list provider and attached to the certificate, would serve as a kinda CA: one could compare their list to our "trusted" list, and if there is an acceptable overlap, the certificate would be considered trustworthy. There exist algorithms for performing a decentralized vote, and ones for distributed certificate minting, so it is technically possible to create such certificate. It then could be linked in the feed, and checked only when a conflict ever arises - then resolution is simply a problem of comparing certificate creation times. 

### Specifics - diff this with the e52d2ad [readme](https://github.com/tanrax/org-social-relay/blob/e52d2adcfe1915a32f9935f522e1d4c4bef3230b/README.md) - or look for quotes

## Introduction

Org Social Relay is a P2P system that acts as an intermediary between all [Org Social](https://github.com/tanrax/org-social) files. It scans the network, creating an index of users, mentions, replies, groups and threads. This allows you to:

![Diagram](https://mermaid.ink/img/pako:eNp1U1FPgzAQ_ivNJUs0YQu0gzFifNke1Rd9ciym0nOrbpS0kEy3_XcLROkUeLi033fftfeVO0KmBEICG82LLXlapjmx35005aoO5MHSZt2i9TpY1dEB6F-AuUAbRyOyqLjQyhCjMsl3E6U3pOCak4wLTnIlVJv52NDBS7DqEteXFB2i6LCKDqvYsIr1qbqOVI4HaYOxnQiN4618V519ZDy-bR3rwWgPxobrC-x8IpyYypDsn5_OGzU1f60cIqjziA5BXcUl4SiYQzBXcUnQ4aYwLzU2LRly9SqF1JhlluI7NNfunW9swVNjVWVQm5PrYHvH3gwGnv2rpYCk1BV6sEe95_UWjrU2hXKLe0whsUvB9UcKaX62moLnz0rtf2RaVZstJG98Z-yuKgQvcSm5nZcuBXOBeqGqvIQkbCpAcoQDJHROJ1Ewm0Y0CGPqs8CDT0iCkE1iGofRLPSnsV2dPfhqjvQnEZ0GEZ1NWRj54dyPPEAhS6Xv2zFtpvX8DWT3JKA?bgColor=!white)

[Source](/diagram.mmd)

- Receive mentions and replies.
- Have a more comprehensive notification system.
- Read or participate in threads.
- Perform searches (tags and full text).
- Participate in groups. 

## Installation

You need to have Docker and Docker Compose installed.
> Will there be a native version?
### 1. Create a `.env` file based on `env.example`

```bash
cp env.example .env
```

And edit it to your needs.

### 2. Run with Docker Compose

```bash
docker compose up -d
```

## Endpoints for clients
> It seems as though most methods basically serve fully static content - that is great, it means in theory there could also be stripped-down, immutable relays that literally work very rarely, precompute only what can be served statically - with many heuristic simplifications, like not expecting replies for old messages. Then, such "micro-relays" could fully shut down, delegating their functionality to an already running http service - or even uploading the different results to an outside machine to serve. <br>
> This is also a dream for caching if properly configure, isn't it?

### Root

`/` - Basic information about the relay.
> There should be a method for getting relay info?
> Admin contact (for manual intervention), relay version, some stats, etc.

```sh
curl http://localhost:8080/
```

```json
{
    "_links": [
        {"rel": "self", "href": "/", "method": "GET"},
        {"rel": "list-feeds", "href": "/feeds", "method": "GET"},
        {"rel": "add-feed", "href": "/feeds", "method": "POST"},
        {"rel": "get-mentions", "href": "/mentions/?feed={url feed}", "method": "GET"},
        {"rel": "get-replies", "href": "/replies/?post={url post}", "method": "GET"},
        {"rel": "search", "href": "/search?q={query}", "method": "GET"},
        {"rel": "list-groups", "href": "/groups", "method": "GET"},
        {"rel": "get-group-messages", "href": "/groups/{group id}/messages", "method": "GET"},
        {"rel": "register-group-member", "href": "/groups/{group id}/members?feed={url feed}", "method": "POST"}
    ]
}
```
> Not that big of a fan of overloading, with different behaviour on GET/POST - though I'm not that into backends, maybe its common?
> I think it would be more understandable if it was split though.

### List feeds

`/feeds` - List all registered feeds.
> These are only the feeds that the relay manages, right?

```sh
curl http://localhost:8080/feeds
```

```json
{
    "type": "Success",
    "errors": [],
    "data": {
        "feeds": [
            "https://example.com/social.org",
            "https://another-example.com/social.org"
        ]
    }
}
```

### Add feed

`/feeds` - Add a new feed to be scanned.

```sh
curl -X POST http://localhost:8080/feeds -d '{"feed": "https://example.com/path/to/your/file.org"}' -H "Content-Type: application/json"
```

```json
{
    "type": "Success",
    "errors": [],
    "data": {
        "feed": "https://example.com/path/to/your/file.org"
    }
}
```


### Get mentions

`/mentions/?feed={url feed}` - Get mentions for a given feed.

```sh
curl http://localhost:8080/mentions/?feed=https://example.com/social.org
```

```json
{
    "type": "Success",
    "errors": [],
    "data": [
        "https://foo.org/social.org#2025-02-03T23:05:00+0100",
        "https://bar.org/social.org#2025-02-04T10:15:00+0100",
        "https://baz.org/social.org#2025-02-05T08:30:00+0100"
    ],
    "meta": {
        "feed": "https://example.com/social.org",
        "total": 3,
        "version": "123"
    }
}
```

The `version` in the `meta` field is a unique identifier for the current state of mentions for the given feed. You can use it to check if there are new mentions since your last request.

### Get replies/threads

`/replies/?post={url post}` - Get replies for a given post. This will return a tree structure with all the replies to posts in the given feed. If you want to see the entire tree, you must use the meta `parent` as a  `post`.

```sh
curl http://localhost:8080/replies/?post=https://foo.org/social.org#2025-02-03T23:05:00+0100
```

```json
{
    "type": "Success",
    "errors": [],
    "data": [
        {
            "post": "https://bar.org/social.org#2025-02-02T14:30:00+0100",
            "children": [
                {
                    "post": "https://baz.org/social.org#2025-02-03T09:45:00+0100",
                    "children": []
                },
                {
                    "post": "https://qux.org/social.org#2025-02-04T16:20:00+0100",
                    "children": [
                        {
                            "post": "https://quux.org/social.org#2025-02-05T11:10:00+0100",
                            "children": []
                        }
                    ]
                }

            ]
        },
        {
            "post": "https://corge.org/social.org#2025-02-03T18:00:00+0100",
            "children": []
        }
    ],
    "meta": {
        "parent": "https://moo.org/social.org#2025-02-03T23:05:00+0100",
        "version": "123"
    }
}
```

The `version` in the `meta` field is a unique identifier for the current state of replies for the given post. You can use it to check if there are new replies since your last request.

### Search

`/search?q={query}` - Search posts by free text.
`/search?tag={tag}` - Search posts by tag.
> Maybe regex too? FZF seems like too much

```sh
curl http://localhost:8080/search?q=emacs
```

Optional parameters:

- `page`: Page number (default: 1)
- `perPage`: Results per page (default: 10, max: 50)

```json
{
    "type": "Success",
    "errors": [],
    "data": [
        "https://foo.org/social.org#2025-02-03T23:05:00+0100",
        "https://bar.org/social.org#2025-02-04T10:15:00+0100",
        "..."
    ],
    "meta": {
        "version": "123",
        "query": "example",
        "total": 150,
        "page": 1,
        "perPage": 10,
        "hasNext": true,
        "hasPrevious": false,
        "links": {
            "next": "/search?q=example&page=2",
            "previous": null
        }
    }
}
```

The `version` in the `meta` field is a unique identifier for the current state of the search index. You can use it to check if there are new results since your last request.

### List groups

`/groups` - List all groups from the relay.
> There will have to be an interface for adding groups too, though it maybe should have some limitations on it
> Also, maybe it should be `/group/list` or something like this, for the `/group/{group id}` sake - it seems cleaner

```sh
curl http://localhost:8080/groups
```

```json
{
    "type": "Success",
    "errors": [],
    "data": [
        {
            "id": 1,
            "name": "emacs",
            "description": "A group for Emacs enthusiasts.",
            "members": 120,
            "posts": 450
        },
        {
            "id": 2,
            "name": "org-mode",
            "description": "Discuss everything about Org mode.",
            "members": 200,
            "posts": 800
        }
    ]
}
```

### Register as group member

`/groups/{group id}/members?feed={url feed}` - Register a feed as a member of a group.

> There needs to be a way to list group members

```sh
curl -X POST "http://localhost:8080/groups/1/members?feed=https://example.com/social.org"
```

```json
{
    "type": "Success",
    "errors": [],
    "data": {
        "group": "emacs",
        "feed": "https://example.com/social.org"
    }
}
```

### Get group messages

`/groups/{group id}/messages` - Get messages from a group.

```sh
curl http://localhost:8080/groups/1/messages
```

```json
{
    "type": "Success",
    "errors": [],
    "data": [
        {
            "post": "https://foo.org/social.org#2025-02-03T23:05:00+0100",
            "children": []
        },
        {
            "post": "https://bar.org/social.org#2025-02-04T10:15:00+0100",
            "children": [
                {
                    "post": "https://baz.org/social.org#2025-02-05T08:30:00+0100",
                    "children": []
                }
            ]
        }
    ],
    "meta": {
        "group": "emacs",
        "total": 2,
        "version": "123"
    }
}
```

The `version` in the `meta` field is a unique identifier for the current state of messages in the group. You can use it to check if there are new messages since your last request.

> Version is going to be some hash of the message state, right?
> Maybe then there should also be a way to get per-feed version, for local caching sake.

## Technical information

You can find the public Relay list in `https://cdn.jsdelivr.net/gh/tanrax/org-social/org-social-relay-list.txt`.
> Relays should provide their own relay list to the outside, for extra decentralization.

### Cron

> Timings should be configurable by the relay admin. <br>
> Also, I've seen cases where repeatable fetches from some feeds ip-bans me ther for some time (it might get worse for non-residential ips on relays).
> So, maybe there should be a per-feed (maybe even dynamic) scan frequency. <br>
> For scan failures (for whatever reason), using old results is a possibiltiy (though it would have to be communicated through the api), and scheduling an extra rescan could be a possibility.

#### Scan feeds

Every 10 minutes, Relay will scan all registered feeds for new posts.
> There needs to be "last-updated" meta field with the time the scan happened.
> Sometimes a specific feed might be unresponsive. Then

#### Scan other nodes

Every hour, Relay will search for new users on other nodes.

#### Discover new feeds

Every day, Relay analyzes the feeds of all registered users to discover new feeds they follow.
> This should be per-day only for the global users, the feeds that get fetched because of groups/local feeds can get their profiles updated then with basically no effort. <br>
> Also, maybe discover new groups? <br>
