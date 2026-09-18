<%@page contentType="application/json;charset=gbk"%>
<%@page import="com.api.formmode.cache.*"%>
<%@page import="weaver.workflow.workflow.WorkflowBillComInfo"%>
<%
    int ok = 0, fail = 0;
    StringBuilder sb = new StringBuilder();
    try { new CubeInterfaceConfigComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("CubeInterfaceConfigComInfo:").append(e.getMessage()).append(";"); }
    try { new CubeInterfaceUserComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("CubeInterfaceUserComInfo:").append(e.getMessage()).append(";"); }
    try { new CubeMindComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("CubeMindComInfo:").append(e.getMessage()).append(";"); }
    try { new CustomSearchComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("CustomSearchComInfo:").append(e.getMessage()).append(";"); }
    try { new CustomSerachBatchSetComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("CustomSerachBatchSetComInfo:").append(e.getMessage()).append(";"); }
    try { new CustomTreeComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("CustomTreeComInfo:").append(e.getMessage()).append(";"); }
    try { new CustomTreeDetailComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("CustomTreeDetailComInfo:").append(e.getMessage()).append(";"); }
    try { new E8FormComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("E8FormComInfo:").append(e.getMessage()).append(";"); }
    try { new E8SearchComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("E8SearchComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeAppComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeAppComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeBrowserComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeBrowserComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeBrowserTypeComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeBrowserTypeComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeExpandPageComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeExpandPageComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeFormComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeFormComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeFormFieldComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeFormFieldComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeFormFieldEncryptComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeFormFieldEncryptComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeRemindComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeRemindComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeReportComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeReportComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeResourceComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeResourceComInfo:").append(e.getMessage()).append(";"); }
    try { new ModeTriggerWorkflowSetComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("ModeTriggerWorkflowSetComInfo:").append(e.getMessage()).append(";"); }
    try { new PageComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("PageComInfo:").append(e.getMessage()).append(";"); }
    try { new WorkflowToModeSetComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("WorkflowToModeSetComInfo:").append(e.getMessage()).append(";"); }
    try { new WorkflowBillComInfo().removeCache(); ok++; } catch (Exception e) { fail++; sb.append("WorkflowBillComInfo:").append(e.getMessage()).append(";"); }
    String detail = sb.length() > 0 ? sb.toString() : "all ok";
    out.print("{\"status\":\"1\",\"ok\":" + ok + ",\"fail\":" + fail + ",\"detail\":\"" + detail + "\"}");
%>
