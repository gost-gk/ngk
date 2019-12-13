var app = angular.module('app', ['ngRoute']);


const DEFAULT_FILTER = `// quick and dirty filter agains guest spam
// it can reject normal links, but who cares...
if ((comment.user_id == 1) && comment.text.match('http://')) {
    return true;
}
if (comment.user_id == 25580 && comment.text.indexOf("Моментальный магазин закладок LegalRF") >= 0) {
    return true;
}
if (comment.user_id == 25580 && comment.text.indexOf("Хелло, Вы спрашивали, как заказать") >= 0) {
    return true;
}
if (comment.user_id == 25580 && comment.text.indexOf("Привет, ваш регион представляется как Краснодар") >= 0) {
    return true;
}
if (comment.user_id == 25580 && comment.text.indexOf("Онлайн-магазин Китайская медицина") >= 0) {
    return true;
}
if (comment.user_id == 25580 && comment.text.indexOf("великолепная природа от тропиков и аризонской пустыни до Ниагарских водопадов") >= 0) {
    return true;
}
if (comment.user_id == 25580 && comment.text.match('^_+$')) {
    return true;
}
return false;`;

const SEARCH_LIMIT = 50;

function formatDate(timestamp_seconds) {
    var date = new Date(timestamp_seconds * 1000);
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
    var timeout, context, args, result;
    var previous = 0;
    if (!options) options = {};

    var later = function() {
      previous = options.leading === false ? 0 : Date.now();
      timeout = null;
      result = func.apply(context, args);
      if (!timeout) context = args = null;
    };

    var throttled = function() {
      var now = Date.now();
      if (!previous && options.leading === false) previous = now;
      var remaining = wait - (now - previous);
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
    var popupStack = [];
    var currentPopup = null;
    var touchMode = false;

    function switchToTouchMode() {
        touchMode = true;
        angular.element(document.body).bind('touchstart', function () {
            currentPopup = null;
            closePopups();
        });
    }

    function loadPopup(scope, anchor) {
        if (scope.commentId) {
            var request = {
                method: 'GET',
                url: '/ngk/api/comments',
                params: {id: scope.commentId}
            };

            var template =
                `<div class="comment-popup comment">
                    <ng-include src="'comment-template-base'"></ng-include>
                </div>`;

            $http(request).then(function(response) {
                var comment = response.data[0];
                comment.text = $sce.trustAsHtml(comment.text);
                comment.avatar_url = makeAvatarUrl(comment.user_avatar);
                comment.posted_local = formatDate(comment.posted_timestamp);
                comment.source = $sce.trustAsHtml(formatSource(comment.source, "Коммент"));
                scope.comment = comment;
                showPopup(scope, anchor, template);
            })
        } else {
            var request = {
                method: 'GET',
                url: '/ngk/api/post/' + scope.postId,
                params: {no_comments: true}
            };

            var template =
                `<div class="comment-popup comment">
                <ng-include src="'post-template-base'"></ng-include>
                </div>`;

            $http(request).then(function(response) {
                var post = response.data;
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
        var popup = angular.element($compile(template)(scope));

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
        var y = anchor[0].getBoundingClientRect().top + window.scrollY;
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

app.config(function($routeProvider, $rootScopeProvider) {
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
    
    $routeProvider.when('/:postId', {
        'templateUrl': 'post.html',
        'controller': 'PostController'
    });

    $rootScopeProvider.digestTtl(1000);
});

function makeAvatarUrl(hash) {
    var defaultAvatar = location.protocol + "//" + location.host + "/ngk/default.png";
    if (!hash)
        return defaultAvatar;
    return location.protocol + '//www.gravatar.com/avatar/' + hash + '?size=48&r=pg&default=' + encodeURIComponent(defaultAvatar);
}

function getIgnoredUsers() {
    var ignoredUsers = null;
    try {
        var ignoredUsers = JSON.parse(localStorage.getItem("ignoredUsers"));
    } catch (e) {
    }
    return ignoredUsers || {};
}

function ignoreUser(route, user_id, user_name) {
    var ignoredUsers = getIgnoredUsers();
    ignoredUsers[user_id] = user_name;
    localStorage.setItem("ignoredUsers", JSON.stringify(ignoredUsers));
    console.log(ignoredUsers);

    if (route && route.reload) {
        route.reload();
    }
}
    
function getLastViewedComments() {
    var lastViewed = null;
    try {
        var lastViewed = JSON.parse(localStorage.getItem("lastViewed"));
    } catch (e) {
    }
    return lastViewed || {};
}

function setLastViewedComments(lastViewed) {
    localStorage.setItem("lastViewed", JSON.stringify(lastViewed));
}

app.controller('CommentsController', function($scope, $http, $sce, $interval, $route) {
    $scope.comments = [];
    var minDate = null;
    var seen = {};
    var limit = 20;
    var notifier = new Notifier();

    var spamFilterString = localStorage.getItem("spamFilter") || DEFAULT_FILTER;
    var isSpam = new Function("comment", spamFilterString);
    
    function updateViewedComments() {
        var lastViewed = getLastViewedComments();
        for (var j = 0; j < $scope.comments.length; ++j) {
            var comment = $scope.comments[j];
            var lastViewedInPost = lastViewed[comment.post_id] || 0;
            comment.is_new = comment.id > lastViewedInPost;
        }
    }
    
    function insertComment(comment) {
        if (seen[comment.id])
            return;
        seen[comment.id] = true;

        comment.posted_local = formatDate(comment.posted_timestamp);
        comment.source = $sce.trustAsHtml(formatSource(comment.source, "Коммент"));
        
        if (minDate == null || comment.posted < minDate)
            minDate = comment.posted;

        if (isSpam(comment))
            return;

        comment.text = $sce.trustAsHtml(comment.text);
        comment.avatar_url = makeAvatarUrl(comment.user_avatar);
        comment.is_new = false;

        notifier.onCommentAdded();

        for (var j = 0; j < $scope.comments.length; ++j) {
            if (comment.id > $scope.comments[j].id) {
                $scope.comments.splice(j, 0, comment);
                return;
            }
        }

        $scope.comments.push(comment);
    }

    function loadComments(beforeDate) {
        var request = {
            method: 'GET',
            url: '/ngk/api/comments',
            params: {}
        };

        if (beforeDate)
            request.params.before = beforeDate;

        var ignoredUsers = getIgnoredUsers();
        if (ignoredUsers) {
            var ignore = [];
            for (var k in ignoredUsers)
                ignore.push(k);
            ignore = ignore.join(",");
            if (ignore)
                request.params.ignore = ignore;
        }

        $http(request).then(function(response) {
            for (var i = 0; i < response.data.length; ++i)
                insertComment(response.data[i]);

            updateViewedComments();

            if ($scope.comments.length < limit)
                loadMoreComments();
        });
    }

    function loadNewComments() {
        loadComments(null);
    }

    function loadMoreComments() {
        loadComments(minDate);
    }

    $scope.loadMoreComments = function() {
        limit += 20;
        loadMoreComments();
        console.log('Loading more.');
    }

    $scope.ignoreUser = ignoreUser.bind(undefined, $route);

    $scope.unignoreAllUsers = function() {
        localStorage.removeItem("ignoredUsers");
        $route.reload();
    }

    loadComments(null);

    var updateTimer = $interval(loadNewComments, 5000);
    var infScroll = throttle(function() {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            $scope.loadMoreComments();
        }
    }, 1500);
    
    var infScrollListener = function(ev) {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            infScroll();
        }
    };
    
    window.addEventListener('scroll', infScrollListener);
    
    $scope.$on('$destroy', function() {
        $interval.cancel(updateTimer);
        infScroll.cancel();
        window.removeEventListener('scroll', infScrollListener);
    });
});


app.controller('PostController', function($scope, $http, $sce, $routeParams, $timeout, $anchorScroll, $route) {
    var request = {
        method: 'GET',
        url: '/ngk/api/post/' + $routeParams.postId,
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

        var comments = [];
        var known_comments = {};

        var lastViewed = getLastViewedComments();
        var lastViewedInPost = lastViewed[response.data.id] || 0;
        var ignoredUsers = getIgnoredUsers();

        for (var j = 0; j < response.data.comments.length; ++j) {
            var comment = response.data.comments[j];
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

        var maxLevel = 20;
        function flatten(level, comments) {
            var out = [];
            for (var j = 0; j < comments.length; j++) {
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
            var res = [];
            for (var j = 0; j < comments.length; ++j) {
                var comment = comments[j];
                comment.children = filterIgnoredComments(comment.children);
                if ((comment.user_id in ignoredUsers) && (comment.children.length == 0))
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
});

app.controller('SearchController', function($scope, $routeParams, $http, $sce, $interval, $route) {
    $scope.result = [];

    var examples = [
        "карманный лев",
        "вореции и кобенации",
        "царский анролл",
        "бесконечный сток",
        "тарасоформатирование",
        "какой багор",
        "крестоблядство"
    ];

    var examplesUsername = [
        "bormand",
        "guest8",
        "wvxvw"
    ];
    
    $scope.example = examples[Math.floor(examples.length * Math.random())];
    $scope.exampleUsername = examplesUsername[Math.floor(examplesUsername.length * Math.random())];
    $scope.state = 'NO_QUERY';
    $scope.searchComplete = false;
    
    var doSearchRequest = function(query, username, beforeTimestamp, callback) {
        var request = {
            method: 'GET',
            url: '/ngk/api/search',
            params: {query: query, username: username, before: beforeTimestamp}
        };

        $http(request).then(function(response) {
            for (var i = 0; i < response.data.length; ++i) {
                var comment = response.data[i];
                comment.posted_local = formatDate(comment.posted_timestamp);
                comment.source = $sce.trustAsHtml(formatSource(comment.source, "Коммент"));
                comment.text = $sce.trustAsHtml(comment.text);
                comment.avatar_url = makeAvatarUrl(comment.user_avatar);
            }
            callback(response);
        });
    };
    
    $scope.search = function() {
        $scope.searchComplete = false;
        $scope.state = 'IN_PROGRESS';
        
        doSearchRequest($scope.query, $scope.username, null, function(response) {
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
    
    
    if ($routeParams.user !== undefined) {
        $scope.username = $routeParams.user;
        $scope.search();
    }
    
    var infScroll = throttle(function() {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            $scope.loadMoreResults();
        }
    }, 1500);
    
    var infScrollListener = function(ev) {
        if ((window.innerHeight + window.pageYOffset) >= document.body.offsetHeight) {
            infScroll();
        }
    };
    
    window.addEventListener('scroll', infScrollListener);
    
    $scope.$on('$destroy', function() {
        infScroll.cancel();
        window.removeEventListener('scroll', infScrollListener);
    });
    
    $scope.ignoreUser = ignoreUser.bind(undefined, undefined);
});


app.controller('SettingsController', function($scope, $http, $sce, $interval, $route) {
    var spamFilter = localStorage.getItem("spamFilter") || DEFAULT_FILTER;

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