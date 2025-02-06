M = {}

function M.telescope_image_preview()
  local supported_images = { "svg", "png", "jpg", "jpeg", "gif", "webp", "avif" }

  local is_image_preview = false
  local image = nil
  local last_file_path = ""

  local is_supported_image = function(path)
    local split_path = vim.split(path:lower(), ".", { plain = true })
    local extension = split_path[#split_path]
    return vim.tbl_contains(supported_images, extension)
  end

  local create_image = function(path, winid, buf)
    image = require("image").hijack_buffer(path, winid, buf)

    if not image then
      return
    end

    -- get window size and set image size
    local width = vim.api.nvim_win_get_width(winid)
    local height = vim.api.nvim_win_get_height(winid)

    vim.schedule(function()
      image:render({ width = width, height = height })
    end)

    is_image_preview = true
  end

  local delete_image = function()
    if not image then
      return
    end

    image:clear()

    is_image_preview = false
  end

  local function defaulter(f, default_opts)
    default_opts = default_opts or {}
    return {
      new = function(opts)
        if require("telescope.config").values.preview == false and not opts.preview then
          return false
        end
        opts.preview = type(opts.preview) ~= "table" and {} or opts.preview
        if type(require("telescope.config").values.preview) == "table" then
          for k, v in pairs(require("telescope.config").values.preview) do
            opts.preview[k] = vim.F.if_nil(opts.preview[k], v)
          end
        end
        return f(opts)
      end,
      __call = function()
        local ok, err = pcall(f(default_opts))
        if not ok then
          error(debug.traceback(err))
        end
      end,
    }
  end

  -- NOTE: Add teardown to cat previewer to clear image when close Telescope
  local file_previewer = defaulter(function(opts)
    opts = opts or {}
    ---@diagnostic disable-next-line: undefined-field
    local cwd = opts.cwd or vim.loop.cwd()
    return require("telescope.previewers").new_buffer_previewer({
      title = "File Preview",
      dyn_title = function(_, entry)
        return require("plenary.path"):new(require("telescope.from_entry").path(entry, true)):normalize(cwd)
      end,

      get_buffer_by_name = function(_, entry)
        return require("telescope.from_entry").path(entry, true)
      end,

      define_preview = function(self, entry, _)
        local p = require("telescope.from_entry").path(entry, true)
        if p == nil or p == "" then
          return
        end

        require("telescope.config").values.buffer_previewer_maker(p, self.state.bufnr, {
          bufname = self.state.bufname,
          winid = self.state.winid,
          preview = opts.preview,
        })
      end,

      teardown = function(_)
        if is_image_preview then
          delete_image()
        end
      end,
    })
  end, {})

  local buffer_previewer_maker = function(filepath, bufnr, opts)
    -- NOTE: Clear image when preview other file
    if is_image_preview and last_file_path ~= filepath then
      delete_image()
    end

    last_file_path = filepath

    if is_supported_image(filepath) then
      create_image(filepath, opts.winid, bufnr)
    else
      require("telescope.previewers").buffer_previewer_maker(filepath, bufnr, opts)
    end
  end

  return { buffer_previewer_maker = buffer_previewer_maker, file_previewer = file_previewer.new }
end

return {}
