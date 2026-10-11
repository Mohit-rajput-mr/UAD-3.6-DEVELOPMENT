/* The editor shell's commands (DR phase 2, step S1 / T-272;
   _work/dr/PHASE2_SHELL_PLAN.md "Control inventory").  Registers, through
   UADShell.commands, a command for every control in the inventory: the view
   tabs, the Deliver actions, the adopted report-toolbar originals and the new
   Home groups.  A stub until S1 lands; S0a gives it its <script> tag so no
   later step edits index.html. */
(function(){
  if(!window.UADShell||!UADShell.enabled()) return;
})();
