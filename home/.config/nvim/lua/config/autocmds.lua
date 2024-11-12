-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
-- Add any additional autocmds here

local augroup = vim.api.nvim_create_augroup
local autocmd = vim.api.nvim_create_autocmd

-- Don't continue comments with o and O
autocmd("BufEnter", {
  pattern = { "*" },
  callback = function()
    vim.opt.formatoptions:remove({ "c", "r", "o" })
  end,
  group = augroup("no_comment_continue", { clear = true }),
  desc = "Don't new line comments",
})

-- no No Name Buffer
autocmd({ "BufReadPre", "BufReadPost" }, {
  pattern = { "*" },
  callback = function()
    local bufs = vim.fn.getbufinfo({ buflisted = 1 })
    for _, buf in pairs(bufs) do
      -- If the buffer is unnamed
      if buf.name == "" then
        local lines = vim.api.nvim_buf_get_lines(buf.bufnr, 0, -1, false)
        local num_chars = 0
        for _, line in pairs(lines) do
          num_chars = num_chars + #line
        end
        -- If the buffer is empty
        if num_chars == 0 then
          vim.api.nvim_buf_delete(buf.bufnr, { force = true })
        end
      end
    end
  end,
  group = augroup("no_no_name_buffer", { clear = true }),
  desc = "no No Name Buffer",
})

-- Enable <C-l> in terminal
autocmd("TermOpen", {
  desc = "Enable <C-l> in terminal",
  callback = function(ev)
    vim.keymap.set("t", "<C-l>", "<C-l>", { buffer = ev.buf, nowait = true })
  end,
})
