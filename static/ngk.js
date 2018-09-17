var app = angular.module('app', ['ngRoute']);

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
                '<div class="comment-popup comment">' +
                '  <img src="{{comment.avatar_url}}" class="avatar">' +
                '  <div class="content">' +
                '    <div class="info">' +
                '      <a href="http://govnokod.ru/user/{{comment.user_id}}">{{comment.user_name}}</a>' +
                '      насрал в ' +
                '      <a href="http://govnokod.ru/{{comment.post_id}}#comment{{comment.id}}">#{{comment.post_id}}</a>' +
                '      (<a href="#!/{{comment.post_id}}#comment{{comment.id}}">Зеркало на NGK</a>)' +
                '      ({{comment.posted}})' +
                '      <ngk-comment-popup comment-id="{{comment.parent_id}}" post-id="{{comment.post_id}}" />' +
                '    </div>' +
                '    <div class="text" ng-bind-html="comment.text"</div>' +
                '  </div>' +
                '</div>';

            $http(request).then(function(response) {
                var comment = response.data[0];
                comment.text = $sce.trustAsHtml(comment.text);
                comment.avatar_url = makeAvatarUrl(comment.user_avatar);
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
                '<div class="comment-popup comment">' +
                '  <img src="{{post.avatar_url}}" class="avatar">' +
                '  <div class="content">' +
                '    <div class="info">' +
                '      <a href="http://govnokod.ru/user/{{post.user_id}}">{{post.user_name}}</a>' +
                '      насрал в ' +
                '      <a href="http://govnokod.ru/{{post.id}}">#{{post.id}}</a>' +
                '      (<a href="#!/{{post.id}}">Зеркало на NGK</a>)' +
                '      ({{post.posted}})' +
                '    </div>' +
                '    <pre>{{post.code}}</pre>' +
                '    <div class="text" ng-bind-html="post.text"></div>' +
                '  </div>' +
                '</div>';

            $http(request).then(function(response) {
                var post = response.data;
                post.text = $sce.trustAsHtml(post.text);
                post.avatar_url = makeAvatarUrl(post.user_avatar);
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
    return 'http://www.gravatar.com/avatar/' + hash + '?size=48&r=pg&default=' + encodeURIComponent(defaultAvatar);
}

function getIgnoredUsers() {
    var ignoredUsers = null;
    try {
        var ignoredUsers = JSON.parse(localStorage.getItem("ignoredUsers"));
    } catch (e) {
    }
    return ignoredUsers || {};
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

    function isSpam(comment) {
        // quick and dirty filter agains guest spam
        // it can reject normal links, but who cares...
        if ((comment.user_id == 1) && comment.text.match('http://'))
                return true;
        return false;
    }

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
    }

    $scope.ignoreUser = function(user_id, user_name) {
        var ignoredUsers = getIgnoredUsers();
        ignoredUsers[user_id] = user_name;
        localStorage.setItem("ignoredUsers", JSON.stringify(ignoredUsers));
        console.log(ignoredUsers);

        $route.reload();
    }

    $scope.unignoreAllUsers = function() {
        localStorage.removeItem("ignoredUsers");
        $route.reload();
    }

    loadComments(null);

    var updateTimer = $interval(loadNewComments, 5000);
    $scope.$on('$destroy', function() {
        $interval.cancel(updateTimer);
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

        response.data.comments = comments;
        response.data.avatar_url = makeAvatarUrl(response.data.user_avatar);
        response.data.text = $sce.trustAsHtml(response.data.text);

        $scope.post = response.data;

        $timeout(function() { $anchorScroll(); }, 0);
    });

    $scope.ignoreUser = function(user_id, user_name) {
        var ignoredUsers = getIgnoredUsers();
        ignoredUsers[user_id] = user_name;
        localStorage.setItem("ignoredUsers", JSON.stringify(ignoredUsers));
        console.log(ignoredUsers);

        $route.reload();
    }
});

app.controller('SearchController', function($scope, $http, $sce, $interval, $route) {
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

    $scope.example = examples[Math.floor(examples.length * Math.random())];

    $scope.search = function() {
        var request = {
            method: 'GET',
            url: '/ngk/api/search',
            params: {query: $scope.query}
        };

        $http(request).then(function(response) {
            console.log("Got search response");

            for (var i = 0; i < response.data.length; ++i) {
                var comment = response.data[i];
                comment.text = $sce.trustAsHtml(comment.text);
                comment.avatar_url = makeAvatarUrl(comment.user_avatar);
            }

            $scope.result = response.data;
        });
    }
});

