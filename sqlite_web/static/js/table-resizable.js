$(function() {
  $('#content').hover(function(){
      $('#sidebar').hide();
      $('#content').removeClass('col-9').addClass('col');
    }, function(){
      $('#sidebar').show();
      $('#content').addClass('col-9').removeClass('col');
    });

  $("th").each(function(){
    $(this).css('width', ($(this).width() + 10) + 'px');
  });

  $("table").colResizable({
    liveDrag: true,
    resizeMode: 'overflow'
  });
});