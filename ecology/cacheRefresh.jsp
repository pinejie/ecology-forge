<%@page contentType="application/json;charset=gbk"%>
<%@page import="weaver.systeminfo.label.LabelComInfo"%>
<%
    new LabelComInfo().removeLabelCache();
    out.print("{\"status\":\"1\",\"message\":\"Label\u7f13\u5b58\u5df2\u6e05\u9664\"}");
%>
