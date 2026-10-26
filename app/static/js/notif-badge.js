/**
 * @file Unread-notification badge on the nav bell (logged-in pages only).
 * base.html loads this at the end of <body> for signed-in users. It polls the
 * unread count every 45 s and whenever the tab becomes visible again.
 */
(function initNotifBadge() {
  var badge = document.getElementById('notif-badge');
  if (!badge) return;

  /**
   * Fetch the unread count and show it on the badge (hidden when zero).
   * Skips the request while the tab is hidden; network errors are ignored.
   *
   * @returns {void}
   */
  function refresh() {
    if (document.hidden) return;
    fetch('/api/notifications/unread_count', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        if (d.count > 0) { badge.textContent = d.count > 99 ? '99+' : d.count; badge.hidden = false; }
        else { badge.hidden = true; }
      })
      .catch(function () {});
  }

  refresh();
  setInterval(refresh, 45000);                               // 주기 폴링
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
})();
