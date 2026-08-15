# pragma once

# include <string_view>

# include <span>

# include "call.h++"

namespace linux {
  class file {
    public:
      file (std::string_view path, int mode) {
        this->descriptor = linux::call (
          linux::calls::open,
          path.data(),
          mode
        );
      }

      file (int descriptor) {
        this->descriptor = descriptor;
      }

      // Move-only: a copy would close the same fd twice. A moved-from file is
      // inert (descriptor == -1) so its destructor does nothing.
      file (file&& other) noexcept : descriptor (other.descriptor) {
        other.descriptor = -1;
      }
      file& operator= (file&& other) noexcept {
        if (this != &other) {
          if (this->descriptor >= 0)
            linux::call (linux::calls::close, this->descriptor);
          this->descriptor = other.descriptor;
          other.descriptor = -1;
        }
        return *this;
      }
      file (const file&) = delete;
      file& operator= (const file&) = delete;

      // Guard >= 0 so a failed open (negative fd) and a moved-from file are not
      // closed.
      ~file () {
        if (this->descriptor >= 0)
          linux::call (linux::calls::close, this->descriptor);
      }

      template <
        class type,
        unsigned long int size
      > unsigned long read (
        std::span <
          type,
          size
        > data
      ) {
        return linux::call (
          linux::calls::read,
          this->descriptor,
          data.data (),
          data.size ()
        );
      }

      template <
        class type,
        unsigned long int size
      > unsigned long write (
        std::span <
          type,
          size
        > data
      ) {
        return linux::call (
          linux::calls::write,
          this->descriptor,
          data.data (),
          data.size ()
        );
      }

      template <
        class type
      > unsigned long system_control (
        int command,
        type* command_argument
      ) {
        return linux::call (
          linux::calls::ioctl,
          this->descriptor,
          command,
          command_argument
        );
      }

      int descriptor;
    };
}
