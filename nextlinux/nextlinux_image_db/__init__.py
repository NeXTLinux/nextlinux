def load(driver=None, config={}):
    dbobj = None
    for base in [
            "nextlinux.nextlinux_image_db", "nextlinux-modules.nextlinux_image_db"
    ]:
        try:
            module = __import__(base, fromlist=[driver])
            c = getattr(module, driver)
            dbobj = c.load(config=config)
            break
        except AttributeError as err:
            # didn't find the driver, yet
            pass
        except Exception as err:
            raise err

    if not dbobj:
        raise Exception("DB driver not found: " + str(driver))

    return (dbobj)
