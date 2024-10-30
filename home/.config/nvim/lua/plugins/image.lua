local enable_image = os.getenv("KITTY_WINDOW_ID") ~= nil

return {
  {
    "3rd/image.nvim",
    enabled = vim.fn.executable("make") == 1 and vim.fn.executable("magick") == 1,
    lazy = true,
    dependencies = {
      { "leafo/magick", lazy = true },
    },
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
    opts = {
      commands = {
        toggle_preview_lazy_image = function(state)
          if enable_image then
            -- lazy load image.nvim
            local _ = require("image")
          end
          require("neo-tree.sources.filesystem.commands").toggle_preview(state)
        end,
      },
      window = {
        mappings = {
          ["P"] = { "toggle_preview_lazy_image", config = { use_float = false, use_image_nvim = enable_image } },
        },
      },
    },
  },
}
