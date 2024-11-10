local in_kitty = os.getenv("KITTY_WINDOW_ID") ~= nil
local enable_image = vim.fn.executable("make") == 1
  and vim.fn.executable("magick") == 1
  and vim.fn.filereadable("/usr/include/readline/readline.h") == 1
local use_image = in_kitty and enable_image

return {
  {
    "3rd/image.nvim",
    enabled = enable_image,
    lazy = true,
    init = function()
      if not use_image then
        return
      end
      -- Show image
      vim.api.nvim_create_autocmd("BufEnter", {
        pattern = { "*.png", "*.jpg", "*.jpeg", "*.webp", "*.avif" },
        group = vim.api.nvim_create_augroup("show_image", { clear = true }),
        callback = function(event)
          local buf = event.buf
          local win = vim.api.nvim_get_current_win()
          local path = vim.api.nvim_buf_get_name(buf)

          require("image").hijack_buffer(path, win, buf)
        end,
      })
    end,
    opts = {
      backend = "kitty",
      integrations = {
        markdown = {
          enabled = true,
          clear_in_insert_mode = false,
          download_remote_images = false,
          only_render_image_at_cursor = false,
          filetypes = { "markdown", "quarto" }, -- markdown extensions (ie. quarto) can go here
        },
        neorg = { enabled = true },
      },
      max_height_window_percentage = math.huge,
      max_width_window_percentage = math.huge,
      window_overlap_clear_enabled = true, -- toggles images when windows are overlapped
      window_overlap_clear_ft_ignore = { "cmp_menu", "cmp_docs", "fidget", "" },
    },
  },
  {
    "neo-tree.nvim",
    optional = true,
    opts = {
      commands = {
        toggle_preview_lazy_image = function(state)
          if use_image then
            -- lazy load image.nvim
            local _ = require("image")
          end
          require("neo-tree.sources.filesystem.commands").toggle_preview(state)
        end,
      },
      window = {
        mappings = {
          ["P"] = { "toggle_preview_lazy_image", config = { use_float = false, use_image_nvim = use_image } },
        },
      },
    },
  },
}
