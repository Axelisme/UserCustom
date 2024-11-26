local function my_paste()
  return vim.split(vim.fn.getreg('"'), "\n")
end

if os.getenv("SSH_TTY") ~= nil then
  vim.opt.clipboard = "unnamedplus"
  local osc52 = require("vim.ui.clipboard.osc52")
  vim.g.clipboard = {
    name = "OSC 52",
    copy = {
      ["+"] = osc52.copy("+"),
      ["*"] = osc52.copy("*"),
    },
    paste = {
      ["+"] = my_paste,
      ["*"] = my_paste,
    },
  }
end

return {}
