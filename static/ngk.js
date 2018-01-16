var app = angular.module('app', ['ngRoute']);

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

    $routeProvider.when('/:postId', {
        'templateUrl': 'post.html',
        'controller': 'PostController'
    });

    $rootScopeProvider.digestTtl(1000);
});

function makeAvatarUrl(hash) {
    if (!hash)
        return '';
    return 'http://www.gravatar.com/avatar/' + hash + '?size=64';
}

function getIgnoredUsers() {
    var ignoredUsers = null;
    try {
        var ignoredUsers = JSON.parse(localStorage.getItem("ignoredUsers"));
    } catch (e) {
    }
    return ignoredUsers || {};
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
            request.params.ignore = ignore.join(",");
        }

        $http(request).then(function(response) {
            for (var i = 0; i < response.data.length; ++i)
                insertComment(response.data[i]);

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

    loadComments(null);

    var updateTimer = $interval(loadNewComments, 5000);
    $scope.$on('$destroy', function() {
        $interval.cancel(updateTimer);
    });
});

app.controller('PostController', function($scope, $http, $sce, $routeParams) {
    var request = {
        method: 'GET',
        url: '/ngk/api/post/' + $routeParams.postId,
        params: {}
    };

    console.log("Loading post " + $routeParams.postId + "...")
    $http(request).then(function(response) {
        console.log("Got response")

        var comments = [];
        var known_comments = {};

        for (var j = 0; j < response.data.comments.length; ++j) {
            var comment = response.data.comments[j];
            comment.avatar_url = makeAvatarUrl(comment.user_avatar);
            comment.text = $sce.trustAsHtml(comment.text);
            comment.children = [];
            known_comments[comment.id] = comment;
            if (comment.parent_id)
                known_comments[comment.parent_id].children.push(comment);
            else
                comments.push(comment);
        }

        response.data.comments = comments;
        response.data.avatar_url = makeAvatarUrl(response.data.user_avatar);
        response.data.text = $sce.trustAsHtml(response.data.text);

        $scope.post = response.data;
    });
});
