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

app.config(['$routeProvider', function($routeProvider) {
    $routeProvider.when('/', {
        'templateUrl': 'comments.html',
        'controller': 'CommentsController'
    });
}])

app.controller('CommentsController', function($scope, $http, $sce) {
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

    function makeAvatarUrl(hash) {
        if (!hash)
            return '';
        return 'http://www.gravatar.com/avatar/' + hash + '?size=64';
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

        $http(request).then(function(response) {
            for (var i = 0; i < response.data.length; ++i)
                insertComment(response.data[i]);

            if ($scope.comments.length < limit)
                loadMoreComments();
        });
    }

    function loadMoreComments() {
        loadComments(minDate);
    }

    $scope.loadMoreComments = function() {
        limit += 20;
        loadMoreComments();
    }

    loadComments(null);

    setInterval(loadComments, 5000);
});
