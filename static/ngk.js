"use strict";
let app = angular.module('app', ['ngRoute']);


const DEFAULT_FILTER = `// quick and dirty filter agains guest spam
// it can reject normal links, but who cares...
if ((comment.user_id == 1) && comment.text.match('http://')) {
    return true;
}
return false;`;

const SEARCH_LIMIT = 50;
const COMMENTS_LIMIT = 20;
const RESPONSE_PARENTS_LIMIT = 15;

function SocketTransport(socket) {
    this.socket = socket;
    this.isSocketIoConnected = false;

    this.maxId = 0;
    this.maxIdDirty = false;
    this.setMaxId = function(newMaxId) {
        if (newMaxId != this.maxId || this.maxIdDirty) {
            this.maxId = newMaxId;
            if (this.isSocketIoConnected) {
                this.socket.emit('set_max_id', newMaxId, (function() { this.maxIdDirt = false; }).bind(this));
            } else {
                this.maxIdDirty = true;
            }
        }
    };

    this.disconnect = function() {
        this.socket.disconnect();
    }

    this.onConnect = undefined;
    this.onDisconnect = undefined;
    this.onData = undefined;

    socket.on('connect', (function() {
        console.log('Websockets connected.');
        this.isSocketIoConnected = true;
        this.setMaxId(this.maxId);
        if (this.onConnect) {
            this.onConnect();
        }
    }).bind(this));

    socket.on('disconnect', (function() {
        console.log('Websockets disconnected.');
        this.isSocketIoConnected = false;
        if (this.onDisconnect) {
            this.onDisconnect();
        }
    }).bind(this));
    
    socket.on('new_comments', (function(data) {
        if (this.onData) {
            this.onData(data);
        } else {
            console.log('New_comments arrived, but no dataHandler was set', data);
        }
    }).bind(this));
}

function formatDate(timestamp_seconds) {
    let date = new Date(timestamp_seconds * 1000);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

function formatSource(source, element) {
    switch(source) {
        case 0: return "";
        case 1: return "<span title=\"" + element + " с Webarchive\">WA</span>";
        case 2: return "<span title=\"" + element + " с Хуза\">XYZ</span>";
        default: return "";
    }
}

// Source: https://github.com/jashkenas/underscore/blob/master/underscore.js
function throttle(func, wait, options) {
    let timeout, context, args, result;
    let previous = 0;
    if (!options) options = {};

    let later = function() {
      previous = options.leading === false ? 0 : Date.now();
      timeout = null;
      result = func.apply(context, args);
      if (!timeout) context = args = null;
    };

    let throttled = function() {
      let now = Date.now();
      if (!previous && options.leading === false) previous = now;
      let remaining = wait - (now - previous);
      context = this;
      args = arguments;
      if (remaining <= 0 || remaining > wait) {
        if (timeout) {
          clearTimeout(timeout);
          timeout = null;
        }
        previous = now;
        result = func.apply(context, args);
        if (!timeout) context = args = null;
      } else if (!timeout && options.trailing !== false) {
        timeout = setTimeout(later, remaining);
      }
      return result;
    };

    throttled.cancel = function() {
      clearTimeout(timeout);
      previous = 0;
      timeout = context = args = null;
    };

    return throttled;
};

app.directive('ngkCommentPopup', function ($sce, $compile, $http) {
    let popupStack = [];
    let currentPopup = null;
    let touchMode = false;

    function switchToTouchMode() {
        touchMode = true;
        angular.element(document.body).bind('touchstart', function () {
            currentPopup = null;
            closePopups();
        });
    }

    function loadPopup(scope, anchor) {
        if (scope.commentId) {
            let request = {
                method: 'GET',
                url: '/api/comments',
                params: {id: scope.commentId}
            };

            let template =
                `<div class="comment-popup comment">
                    <ng-include src="'comment-template-base'"></ng-include>
                </div>`;

            $http(request).then(function(response) {
                let comment = response.data[0];
                comment.text = $sce.trustAsHtml(comment.text);
                comment.avatar_url = makeAvatarUrl(comment.user_avatar);
                comment.posted_local = formatDate(comment.posted_timestamp);
                comment.source = $sce.trustAsHtml(formatSource(comment.source, "Коммент"));
                scope.comment = comment;
                showPopup(scope, anchor, template);
            })
        } else {
            let request = {
                method: 'GET',
                url: '/api/post/' + scope.postId,
                params: {no_comments: true}
            };

            let template =
                `<div class="comment-popup comment">
                <ng-include src="'post-template-base'"></ng-include>
                </div>`;

            $http(request).then(function(response) {
                let post = response.data;
                post.text = $sce.trustAsHtml(post.text);
                post.avatar_url = makeAvatarUrl(post.user_avatar);
                post.posted_local = formatDate(post.posted_timestamp);
                post.source = $sce.trustAsHtml(formatSource(post.source, "Пост"));
                scope.post = post;
                showPopup(scope, anchor, template);
            })
        }
    }

    function showPopup(scope, anchor, template) {
        let popup = angular.element($compile(template)(scope));

        angular.element(document.body).append(popup);

        popupStack.push(popup[0]);

        popup.bind('mouseenter', function () {
            currentPopup = popup[0];
        });
        popup.bind('mouseleave', function () {
            currentPopup = null;
            if (!touchMode)
                setTimeout(closePopups, 200);
        });
        popup.bind('touchstart', function () {
            currentPopup = popup[0];
            closePopups();
            event.stopPropagation();
        });
        let y = anchor[0].getBoundingClientRect().top + window.scrollY;
        popup[0].style.left = '5%';
        popup[0].style.top = y + 'px';
    }

    function closePopups() {
        while (popupStack.length > 0) {
            if (popupStack[popupStack.length - 1] == currentPopup)
                return;
            angular.element(popupStack.pop()).remove();
        }
    }

    return {
        template: "<span>#</span>",
        scope: {
            commentId: '@',
            postId: '@'
        },
        link: function (scope, element, attrs) {
            element.bind('mouseenter', function () {
                loadPopup(scope, element);
            });
            element.bind('mouseleave', function () {
                if (!touchMode) {
                    setTimeout(closePopups, 200);
                }
            });
            element.bind('touchstart', function (event) {
                if (!touchMode)
                    switchToTouchMode();
                loadPopup(scope, element);
                event.stopPropagation();
            })
        }
    }
});

function Notifier() {
    this.comments = 0;
    this.hasFocus = true;
    this.titleBackup = null;

    this.restoreTitle = function() {
        if (this.titleBackup != null) {
            document.title = this.titleBackup;
            this.titleBackup = null;
        }

        if (this.comments > 0) {
            setTimeout(this.updateTitle.bind(this), 1000);
        }
    }

    this.updateTitle = function() {
        if ((this.comments > 0) && (this.titleBackup == null)) {
            this.titleBackup = document.title;
            document.title = "*** " + this.comments + " NEW ***";
            setTimeout(this.restoreTitle.bind(this), 1000);
        }
    }

    this.onCommentAdded = function() {
        if (this.hasFocus)
            return;

        this.comments++;
        this.updateTitle();
    }

    function onFocus() {
        this.hasFocus = true;
        this.comments = 0;
        this.restoreTitle();
    }

    function onFocusLost() {
        this.hasFocus = false;
    }


    window.addEventListener("focus", onFocus.bind(this));
    window.addEventListener("blur", onFocusLost.bind(this));
}

app.config(function($templateRequestProvider, $routeProvider, $rootScopeProvider) {
    $templateRequestProvider.httpOptions({
        headers: {
            'Accept': undefined,  // Fuck Chrome
        }
    });

    $routeProvider.when('/', {
        'templateUrl': 'comments.html',
        'controller': 'CommentsController'
    });

    $routeProvider.when('/search', {
        'templateUrl': 'search.html',
        'controller': 'SearchController'
    });
    
    $routeProvider.when('/settings', {
        'templateUrl': 'settings.html',
        'controller': 'SettingsController'
    });

    $routeProvider.when('/blacklist', {
        'templateUrl': 'blacklist.html',
        'controller': 'BlacklistController'
    });

    $routeProvider.when('/replies/:userName', {
        'templateUrl': 'replies.html',
        'controller': 'RepliesController'
    });
    
    $routeProvider.when('/:postId', {
        'templateUrl': 'post.html',
        'controller': 'PostController'
    });

    $rootScopeProvider.digestTtl(1000);
});

function makeAvatarUrl(hash) {
    let defaultAvatar = location.protocol + "//" + location.host + "/img/default.png";
    if (!hash) {
        return defaultAvatar;
    }
    return location.protocol + '//www.gravatar.com/avatar/' + hash + '?size=48&r=pg&default=404';
}

function getLocalStorageObject(name) {
    let obj = null;
    try {
        obj = JSON.parse(localStorage.getItem(name));
    } catch (e) {
    }
    return obj || {};
}

function setLocalStorageObject(name, obj) {
    localStorage.setItem(name, JSON.stringify(obj));
}

function ignoreObject(route, objId, value, localStorageItemName) {
    let ignoredList = getLocalStorageObject(localStorageItemName);
    ignoredList[objId] = value;
    setLocalStorageObject(localStorageItemName, ignoredList);

    if (route && route.reload) {
        route.reload();
    }
}

function unignoreObject(route, objId, localStorageItemName) {
    let ignoredList = getLocalStorageObject(localStorageItemName);
    delete ignoredList[objId];
    setLocalStorageObject(localStorageItemName, ignoredList);

    if (route && route.reload) {
        route.reload();
    }
}

function getIgnoredUsers() {
    return getLocalStorageObject('ignoredUsers');
}

function getIgnoredPosts() {
    return getLocalStorageObject('ignoredPosts');
}

function ignoreUser(route, user_id, user_name) {
    ignoreObject(route, user_id, user_name, 'ignoredUsers');
}

function unignoreUser(route, user_id) {
    unignoreObject(route, user_id, 'ignoredUsers');
}

function ignorePost(route, post_id) {
    ignoreObject(route, post_id, true, 'ignoredPosts');
}

function unignorePost(route, post_id) {
    unignoreObject(route, post_id, 'ignoredPosts');
}

function unignoreEverything($route) {
    console.log('Ignored users: ' + localStorage.getItem('ignoredUsers'));
    console.log('Ignored posts: ' + localStorage.getItem('ignoredPosts'));
    localStorage.removeItem('ignoredUsers');
    localStorage.removeItem('ignoredPosts');
    $route.reload();
}

function setRequestIgnoredParams(request) {
    const ignoredUsers = getIgnoredUsers();
    let ignore = [];
    for (let k in ignoredUsers)
        ignore.push(k);
    ignore = ignore.join(",");
    if (ignore)
        request.params.ignore_u = ignore;

    const ignoredPosts = getIgnoredPosts();
    ignore = [];
    for (let k in ignoredPosts)
        ignore.push(k);
    ignore = ignore.join(",");
    if (ignore)
        request.params.ignore_p = ignore;
}

function getLastViewedComments() {
    return getLocalStorageObject('lastViewed');
}

function setLastViewedComments(lastViewed) {
    setLocalStorageObject('lastViewed', lastViewed);
}

app.controller('CommentsController', function($scope, $http, $sce, $interval, $route) {
    let socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port + '/ngk');
    let transport = new SocketTransport(socket);

    $scope.comments = [];
    let minDate = null;
    let seen = {};
    let limit = COMMENTS_LIMIT;
    let notifier = new Notifier();

    let spamFilterString = localStorage.getItem("spamFilter") || DEFAULT_FILTER;
    let isSpam = new Function("comment", spamFilterString);
    
    function updateViewedComments() {
        let lastViewed = getLastViewedComments();
        for (let comment of $scope.comments) {
            let lastViewedInPost = lastViewed[comment.post_id] || 0;
            comment.is_new = comment.id > lastViewedInPost;
        }
    }
    
    function insertComment(comment) {
        comment.posted_local = formatDate(comment.posted_timestamp);
        comment.source = $sce.trustAsHtml(formatSource(comment.source, "Коммент"));
        
        if (minDate == null || comment.posted < minDate)
            minDate = comment.posted;

        if (isSpam(comment))
            return;
        
        comment.text = $sce.trustAsHtml(comment.text);
        comment.avatar_url = makeAvatarUrl(comment.user_avatar);
        comment.is_new = false;

        if (seen[comment.id] !== undefined) {
            $scope.comments[seen[comment.id]] = comment;
            return;
        }

        notifier.onCommentAdded();
        
        for (let j = 0; j < $scope.comments.length; ++j) {
            if (comment.id > $scope.comments[j].id) {
                $scope.comments.splice(j, 0, comment);
                seen[comment.id] = j;
                for (let i = j + 1; i < $scope.comments.length; i++) {
                    seen[$scope.comments[i].id] = i;
                }
                return;
            }
        }

        seen[comment.id] = $scope.comments.length;
        $scope.comments.push(comment);
    }

    function loadComments(beforeDate) {
        let request = {
            method: 'GET',
            url: '/api/comments',
            params: {}
        };

        if (beforeDate)
            request.params.before = beforeDate;

        setRequestIgnoredParams(request);

        $http(request).then(function(response) {
            let maxId = 0;
            for (let comment of response.data) {
                insertComment(comment);
                maxId = Math.max(comment.id, maxId);
            }

            if (maxId > transport.maxId) {
                transport.setMaxId(maxId);
            }

            updateViewedComments();

            if ($scope.comments.length < limit) {
                loadMoreComments();
            }
        });
    }

    function loadNewComments() {
        if (!transport.isSocketIoConnected) {
            loadComments(null);
        }
    }

    function loadMoreComments() {
        loadComments(minDate);
    }

    $scope.loadMoreComments = function() {
        limit += COMMENTS_LIMIT;
        loadMoreComments();
        console.log('Loading more.');
    }

    $scope.ignoreUser = ignoreUser.bind(undefined, $route);
    $scope.ignorePost = ignorePost.bind(undefined, $route);
    $scope.unignoreEverything = unignoreEverything.bind(undefined, $route);

    function socketIOHandler(data) {
        const ignoredUsers = getIgnoredUsers();
        const ignoredPosts = getIgnoredPosts();
        let maxId = transport.maxId;
        for (let comment of data) {
            if (!(comment.user_id in ignoredUsers) && !(comment.post_id in ignoredPosts)) {
                insertComment(comment);
            }
            if (comment.id > maxId) {
                maxId = comment.id;
            }
        }

        if (maxId != transport.maxId) {
            transport.setMaxId(maxId);
        }

        updateViewedComments();
    }

    loadComments(null);
    transport.onData = socketIOHandler;

    let updateTimer = $interval(loadNewComments, 5000);
    let infScroll = throttle(function() {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            $scope.loadMoreComments();
        }
    }, 1500);
    
    let infScrollListener = function(ev) {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            infScroll();
        }
    };
    
    window.addEventListener('scroll', infScrollListener);
    
    $scope.$on('$destroy', function() {
        transport.disconnect();
        $interval.cancel(updateTimer);
        infScroll.cancel();
        window.removeEventListener('scroll', infScrollListener);
    });
});

app.controller('RepliesController', function($scope, $http, $sce, $interval, $route, $routeParams) {
    $scope.comments = [];
    $scope.user = $routeParams.userName;
    $scope.isUserValid = true;
    let minDate = null;
    let seenParents = {};
    let seenChildren = {};
    let parents = [];
    let children = {};

    let limit = RESPONSE_PARENTS_LIMIT;
    $scope.someRepliesLoaded = false;
    $scope.allRepliesLoaded = false;
    let notifier = new Notifier();

    let spamFilterString = localStorage.getItem("spamFilter") || DEFAULT_FILTER;
    let isSpam = new Function("comment", spamFilterString);
    const ignoredUsers = getIgnoredUsers();
    function isIgnored(comment) {
        return comment.user_id in ignoredUsers;
    }

    function rebuildComments() {
        console.log('Total replies:', totalChildrenCount());
        $scope.comments = [];

        parents = parents.filter((comment) => children[comment.id]);

        parents.sort(function (first, second) {
            let maxChildIdReducer = function (prevMaxId, child) {
                return (child.id > prevMaxId ? child.id : prevMaxId);
            };
            let maxFirstId = children[first.id].reduce(maxChildIdReducer, 0);
            let maxSecondId = children[second.id].reduce(maxChildIdReducer, 0);
            return maxSecondId - maxFirstId;
        });

        for (let parent of parents) {
            if (children[parent.id].length > 0) {
                children[parent.id].sort(function (a, b) { return a.id - b.id; });
                $scope.comments.push(parent);
                $scope.comments = $scope.comments.concat(children[parent.id]);
            }
        }
    }

    function insertParent(comment) {
        if (seenParents[comment.id]) {
            return;
        }

        seenParents[comment.id] = true;
        handleComment(comment);

        comment.indent = 0;
        comment.is_new = false;
        parents.push(comment);
    }

    function insertChild(comment) {
        if (comment.baseline && (minDate == null || comment.posted < minDate)) {
            minDate = comment.posted;
        }

        if (isSpam(comment)) {
            return;
        }

        if (seenChildren[comment.id]) {
            return;
        }

        if (isIgnored(comment)) {
            return;
        }

        seenChildren[comment.id] = true;
        handleComment(comment);

        comment.indent = 1;
        comment.is_new = true;
        if (children[comment.parent_id]) {  // TODO: defaultdict?
            children[comment.parent_id].push(comment);
        } else {
            children[comment.parent_id] = [comment];
        }
    }

    function totalChildrenCount() {
        let sum = 0;
        for (let parent of parents) {
            sum += (children[parent.id] || []).reduce(function (acc, val) { return acc + 1; }, 0);
        }
        return sum;
    }

    function handleComment(comment) {
        comment.posted_local = formatDate(comment.posted_timestamp);
        comment.source = $sce.trustAsHtml(formatSource(comment.source, "Коммент"));
        comment.text = $sce.trustAsHtml(comment.text);
        comment.avatar_url = makeAvatarUrl(comment.user_avatar);

        notifier.onCommentAdded();
    }

    function loadComments(beforeDate) {
        let request = {
            method: 'GET',
            url: '/api/replies/name/' + encodeURI($routeParams.userName),
            params: {}
        };

        if (beforeDate) {
            request.params.before = beforeDate;
        }

        setRequestIgnoredParams(request);

        $http(request).then(function(response) {
            for (let comment of response.data.parents) {
                insertParent(comment);
            }

            for (let comment of response.data.children) {
                insertChild(comment);
            }

            rebuildComments();
            $scope.someRepliesLoaded = true;
            $scope.allRepliesLoaded = response.data.children.length < RESPONSE_PARENTS_LIMIT;
            if ($scope.allRepliesLoaded) {
                window.removeEventListener('scroll', infScrollListener);
            }
            if (!$scope.allRepliesLoaded && totalChildrenCount() < limit) {
                loadMoreComments();
            }
        });
    }

    function checkUserName() {
        let request = {
            method: 'GET',
            url: '/api/user/name/' + encodeURI($routeParams.userName),
            params: {}
        };

        $http(request).then(function(response) {
            if (response.data.name) {
                $scope.isUserValid = true;
            } else {
                $scope.isUserValid = false;
            }
        });
    }

    function loadNewComments() {
        loadComments(null);
    }

    function loadMoreComments() {
        loadComments(minDate);
    }

    $scope.loadMoreComments = function() {
        limit += RESPONSE_PARENTS_LIMIT;
        loadMoreComments();
        console.log('Loading more.');
    }

    $scope.ignoreUser = ignoreUser.bind(undefined, $route);
    $scope.ignorePost = ignorePost.bind(undefined, $route);
    $scope.unignoreEverything = unignoreEverything.bind(undefined, $route);

    checkUserName();
    loadComments(null);
    
    let infScroll = throttle(function() {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            $scope.loadMoreComments();
        }
    }, 1500);
    
    let infScrollListener = function(ev) {
        if ($scope.someRepliesLoaded
                && (window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            infScroll();
        }
    };
    
    window.addEventListener('scroll', infScrollListener);
    
    $scope.$on('$destroy', function() {
        window.removeEventListener('scroll', infScrollListener);
        infScroll.cancel();
    });
});

app.controller('PostController', function($scope, $http, $sce, $routeParams, $timeout, $anchorScroll, $route) {
    let request = {
        method: 'GET',
        url: '/api/post/' + $routeParams.postId,
        params: {}
    };

    try {
        var isTreeModeEnabled = JSON.parse(localStorage.getItem("treeMode")) || false;
    } catch (e) {
        isTreeModeEnabled = false;
    }

    $scope.enableTreeMode = function (enable) {
        localStorage.setItem("treeMode", JSON.stringify(enable));
        $route.reload();
    }

    console.log("Loading post " + $routeParams.postId + "...")
    $http(request).then(function(response) {
        console.log("Got response")

        let comments = [];
        let known_comments = {};

        let lastViewed = getLastViewedComments();
        let lastViewedInPost = lastViewed[response.data.id] || 0;
        const ignoredUsers = getIgnoredUsers();
        const ignoredPosts = getIgnoredPosts();

        for (let j = 0; j < response.data.comments.length; ++j) {
            let comment = response.data.comments[j];
            comment.posted_local = formatDate(comment.posted_timestamp);
            comment.source = $sce.trustAsHtml(formatSource(comment.source, "Коммент"));
            comment.avatar_url = makeAvatarUrl(comment.user_avatar);
            comment.text = $sce.trustAsHtml(comment.text);
            comment.children = [];
            known_comments[comment.id] = comment;
            if (isTreeModeEnabled && comment.parent_id)
                known_comments[comment.parent_id].children.push(comment);
            else
                comments.push(comment);
            if (comment.id > lastViewedInPost) {
                comment.is_new = true;
                lastViewedInPost = comment.id;
            }
        }

        let maxLevel = 20;
        function flatten(level, comments) {
            let out = [];
            for (let j = 0; j < comments.length; j++) {
                comments[j].indent = Math.min(level, maxLevel);
                out.push(comments[j]);
                out = out.concat(flatten(level + 1, comments[j].children));
            }
            //console.log(comments.length, " -> ", out.length);
            return out;
        }

        if (isTreeModeEnabled)
            comments = flatten(1, comments);

        lastViewed[response.data.id] = lastViewedInPost;
        setLastViewedComments(lastViewed);

        function filterIgnoredComments(comments) {
            let res = [];
            for (let j = 0; j < comments.length; ++j) {
                let comment = comments[j];
                comment.children = filterIgnoredComments(comment.children);
                if (((comment.user_id in ignoredUsers) || (comment.post_id in ignoredPosts))
                        && (comment.children.length == 0))
                    continue;
                res.push(comment);
            }
            return res;
        }

        comments = filterIgnoredComments(comments);

        response.data.posted_local = formatDate(response.data.posted_timestamp);
        response.data.source = $sce.trustAsHtml(formatSource(response.data.source, "Пост"));
        console.log(response.data);
        response.data.comments = comments;
        response.data.avatar_url = makeAvatarUrl(response.data.user_avatar);
        response.data.text = $sce.trustAsHtml(response.data.text);
    
        $scope.post = response.data;

        $timeout(function() { $anchorScroll(); }, 0);
    });

    $scope.ignoreUser = ignoreUser.bind(undefined, $route);
    $scope.ignorePost = ignorePost.bind(undefined, $route);
    $scope.unignoreEverything = unignoreEverything.bind(undefined, $route);
});

app.controller('SearchController', function($scope, $routeParams, $location, $http, $sce, $interval, $route) {
    $scope.result = [];

    let examples = [
        "карманный лев",
        "вореции и кобенации",
        "царский анролл",
        "бесконечный сток",
        "тарасоформатирование",
        "какой багор",
        "крестоблядство"
    ];

    let examplesUsername = [
        "bormand",
        "guest8",
        "wvxvw"
    ];
    
    $scope.example = examples[Math.floor(examples.length * Math.random())];
    $scope.exampleUsername = examplesUsername[Math.floor(examplesUsername.length * Math.random())];
    $scope.state = 'NO_QUERY';
    $scope.searchComplete = false;
    
    let doSearchRequest = function(query, username, beforeTimestamp, callback) {
        let request = {
            method: 'GET',
            url: '/api/search',
            params: {query: query, username: username, before: beforeTimestamp}
        };

        $http(request).then(function(response) {
            for (let i = 0; i < response.data.length; ++i) {
                let comment = response.data[i];
                comment.posted_local = formatDate(comment.posted_timestamp);
                comment.source = $sce.trustAsHtml(formatSource(comment.source, "Коммент"));
                comment.text = $sce.trustAsHtml(comment.text);
                comment.avatar_url = makeAvatarUrl(comment.user_avatar);
            }
            callback(response);
        });
    }; 
    
    let search = function(username, query) {
        $scope.searchComplete = false;
        $scope.state = 'IN_PROGRESS';

        doSearchRequest(query, username, null, function(response) {
            $scope.result = response.data;
            if ($scope.result.length > 0) {
                $scope.state = 'FOUND';
            } else {
                $scope.state = 'NOT_FOUND';
            }
            
            if (response.data.length < SEARCH_LIMIT) {
                $scope.searchComplete = true;
            }
        });
    }

    $scope.search = function() {
        let query = $scope.query || null;
        let username = $scope.username || null;
        if (query == $routeParams.q && username == $routeParams.user) {
            $route.reload();
        } else {
            $location.search({q: query, user: username});
        }
    }
    
    $scope.nextSearch = function(beforeTimestamp) {
        if ($scope.searchComplete) {
            return;
        }
       
        doSearchRequest($scope.query, $scope.username, beforeTimestamp, function(response) {
            $scope.result = $scope.result.concat(response.data);
            if (response.data.length < SEARCH_LIMIT) {
                $scope.searchComplete = true;
            }
        });
    }
    
    $scope.loadMoreResults = function() {
        $scope.nextSearch($scope.result[$scope.result.length - 1].posted_timestamp);
    }
    
    
    if ($routeParams.user !== undefined || $routeParams.q !== undefined) {
        $scope.username = $routeParams.user || null;
        $scope.query = $routeParams.q || null;
        search($scope.username, $scope.query);
    }
    
    let infScroll = throttle(function() {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            $scope.loadMoreResults();
        }
    }, 1500);
    
    let infScrollListener = function(ev) {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            infScroll();
        }
    };
    
    window.addEventListener('scroll', infScrollListener);
    
    $scope.$on('$destroy', function() {
        infScroll.cancel();
        window.removeEventListener('scroll', infScrollListener);
    });
    
    $scope.ignoreUser = ignoreUser.bind(undefined, $route);
    $scope.ignorePost = ignorePost.bind(undefined, $route);
    $scope.unignoreEverything = unignoreEverything.bind(undefined, $route);
});

app.controller('SettingsController', function($scope, $http, $sce, $interval, $route) {
    let spamFilter = localStorage.getItem("spamFilter") || DEFAULT_FILTER;

    $scope.newFilter = spamFilter;
    
    $scope.saveFilter = function() {
        localStorage.setItem("spamFilter", $scope.newFilter);
    };
    
    $scope.resetFilter = function() {
        if (confirm("Точно?")) {
            $scope.newFilter = DEFAULT_FILTER;
            $scope.saveFilter();
        }
    };
});

app.controller('BlacklistController', function($scope, $http, $sce, $interval, $route) {
    $scope.rebuildTable = function() {
        const ignoredUsers = getIgnoredUsers();
        const ignoredPosts = getIgnoredPosts();

        $scope.usersBlacklist = [];
        for (let key in ignoredUsers) {
            $scope.usersBlacklist.push({id: key, name: ignoredUsers[key], pardoned: false});
        }

        $scope.postsBlacklist = [];
        for (let key in ignoredPosts) {
            $scope.postsBlacklist.push({id: key, pardoned: false});
        }
    };

    $scope.unignoreUser = function(user_id) {
        unignoreUser(undefined, user_id);
        for (let user of $scope.usersBlacklist) {
            if (user.id == user_id) {
                user.pardoned = true;
                break;
            }
        }
    };

    $scope.ignoreUser = function(user_id, user_name) {
        ignoreUser(undefined, user_id, user_name);
        for (let user of $scope.usersBlacklist) {
            if (user.id == user_id) {
                user.pardoned = false;
                break;
            }
        }
    };

    $scope.unignorePost = function(post_id) {
        unignorePost(undefined, post_id);
        for (let post of $scope.postsBlacklist) {
            if (post.id == post_id) {
                post.pardoned = true;
                break;
            }
        }
    };

    $scope.ignorePost = function(post_id) {
        ignorePost(undefined, post_id);
        for (let post of $scope.postsBlacklist) {
            if (post.id == post_id) {
                post.pardoned = false;
                break;
            }
        }
    };

    $scope.rebuildTable();
});
