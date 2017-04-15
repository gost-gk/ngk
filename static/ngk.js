var app = angular.module('app', []);

app.controller('CommentsController', function($scope, $http, $sce) {
    $scope.comments = [];
    var minDate = null;
    var seen = {};
    var limit = 20;

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
