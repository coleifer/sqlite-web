$(function() {
  $("th").each(function(){
    $(this).css('width', ($(this).width() + 10) + 'px');
  });
  $("table").colResizable({
    liveDrag: true,
    resizeMode: 'overflow'
  });
});