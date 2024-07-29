-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
-- Add any additional autocmds here

local augroup = vim.api.nvim_create_augroup
local autocmd = vim.api.nvim_create_autocmd

--[[ Mygroup Group ]]
augroup("mygroup", { clear = true })

-- Don't continue comments with o and O
autocmd("BufEnter", {
  pattern = { "*" },
  callback = function()
    vim.opt.formatoptions:remove({ "c", "r", "o" })
  end,
  group = "mygroup",
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
  group = "mygroup",
  desc = "no No Name Buffer",
})
