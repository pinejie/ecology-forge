<%@page contentType="application/json;charset=gbk"%>
<%@page import="weaver.portal.cache.MenuCache"%>
<%
    MenuCache.clearMenu(null);
    out.print("{\"status\":\"1\",\"message\":\"\u83dc\u5355\u7f13\u5b58\u5df2\u6e05\u9664\"}");
%>
